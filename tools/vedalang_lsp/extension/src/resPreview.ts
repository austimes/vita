import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";

interface ResNode {
  id: string;
  label: string;
  kind: "commodity" | "process";
  type?: string;  // commodity kind (carrier/service) or process type
  stage?: string;
}

interface ResEdge {
  from: string;
  to: string;
  kind: "input" | "output";
  commodityId?: string;
}

interface ResGraph {
  nodes: ResNode[];
  edges: ResEdge[];
}

type ViewMode = "roles" | "variants";

export class ResPreviewPanel {
  public static currentPanel: ResPreviewPanel | undefined;
  private static readonly viewType = "vedalangResPreview";

  private readonly panel: vscode.WebviewPanel;
  private readonly client: LanguageClient;
  private readonly extensionUri: vscode.Uri;
  private disposables: vscode.Disposable[] = [];
  private debounceTimer: NodeJS.Timeout | undefined;
  private lastVedaDocument: vscode.TextDocument | undefined;
  private viewMode: ViewMode = "roles";

  public static createOrShow(
    extensionUri: vscode.Uri,
    client: LanguageClient
  ): void {
    const column = vscode.window.activeTextEditor
      ? vscode.window.activeTextEditor.viewColumn
      : undefined;

    if (ResPreviewPanel.currentPanel) {
      ResPreviewPanel.currentPanel.panel.reveal(column);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      ResPreviewPanel.viewType,
      "RES Preview",
      column || vscode.ViewColumn.Two,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      }
    );

    ResPreviewPanel.currentPanel = new ResPreviewPanel(
      panel,
      extensionUri,
      client
    );
  }

  private constructor(
    panel: vscode.WebviewPanel,
    extensionUri: vscode.Uri,
    client: LanguageClient
  ) {
    this.panel = panel;
    this.extensionUri = extensionUri;
    this.client = client;

    // Initialize with the current editor if it's a VedaLang file
    const editor = vscode.window.activeTextEditor;
    if (editor && this.isVedaDocument(editor.document)) {
      this.lastVedaDocument = editor.document;
    }

    this.updateContent();

    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

    // Handle messages from webview
    this.panel.webview.onDidReceiveMessage(
      (message) => {
        if (message.command === "setViewMode") {
          this.viewMode = message.mode as ViewMode;
          this.updateContent();
        }
      },
      null,
      this.disposables
    );

    vscode.workspace.onDidChangeTextDocument(
      (e) => {
        if (this.isVedaDocument(e.document)) {
          this.lastVedaDocument = e.document;
          this.scheduleUpdate();
        }
      },
      null,
      this.disposables
    );

    vscode.window.onDidChangeActiveTextEditor(
      (editor) => {
        if (editor && this.isVedaDocument(editor.document)) {
          this.lastVedaDocument = editor.document;
          this.scheduleUpdate();
        }
      },
      null,
      this.disposables
    );
  }

  private isVedaDocument(doc: vscode.TextDocument): boolean {
    return doc.languageId === "vedalang" || doc.fileName.endsWith(".veda.yaml");
  }

  private scheduleUpdate(): void {
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }
    this.debounceTimer = setTimeout(() => {
      this.updateContent();
    }, 200);
  }

  private async updateContent(): Promise<void> {
    // Use lastVedaDocument if available, otherwise try activeTextEditor
    let doc = this.lastVedaDocument;
    const editor = vscode.window.activeTextEditor;
    if (editor && this.isVedaDocument(editor.document)) {
      doc = editor.document;
      this.lastVedaDocument = doc;
    }

    if (!doc) {
      this.panel.webview.html = this.getWebviewContent("flowchart LR\n    N[No VedaLang file open]");
      return;
    }

    try {
      const graph = await this.client.sendRequest<ResGraph>("veda/resGraph", {
        textDocument: {
          uri: doc.uri.toString(),
        },
        includeVariants: this.viewMode === "variants",
      });

      if (!graph || !graph.nodes || graph.nodes.length === 0) {
        this.panel.webview.html = this.getWebviewContent(
          "flowchart LR\n    N[No processes or commodities found]"
        );
        return;
      }

      const mermaidCode = this.graphToMermaid(graph);
      this.panel.webview.html = this.getWebviewContent(mermaidCode);
    } catch (error) {
      console.error("Failed to get RES graph:", error);
      this.panel.webview.html = this.getErrorContent(
        `Failed to generate RES graph: ${error}`
      );
    }
  }

  private graphToMermaid(graph: ResGraph): string {
    const lines: string[] = ["flowchart LR"];

    // Separate nodes by type
    const commodityNodes: ResNode[] = [];
    const roleNodes: ResNode[] = [];
    const variantNodes: ResNode[] = [];

    for (const node of graph.nodes) {
      if (node.kind === "commodity") {
        commodityNodes.push(node);
      } else if (node.type === "variant") {
        variantNodes.push(node);
      } else {
        roleNodes.push(node);
      }
    }

    const hasVariants = variantNodes.length > 0;

    // Build role -> variants mapping
    const roleToVariants: Map<string, ResNode[]> = new Map();
    for (const v of variantNodes) {
      const parent = (v as unknown as { parentRole?: string }).parentRole;
      if (parent) {
        if (!roleToVariants.has(parent)) {
          roleToVariants.set(parent, []);
        }
        roleToVariants.get(parent)!.push(v);
      }
    }

    // Render role nodes (with subgraphs if variants present)
    for (const node of roleNodes) {
      const safeId = this.sanitizeId(node.id);
      const safeLabel = this.sanitizeLabel(node.label || node.id);

      if (hasVariants && roleToVariants.has(node.id)) {
        lines.push(`    subgraph ${safeId}[${safeLabel}]`);
        for (const variant of roleToVariants.get(node.id)!) {
          const vSafeId = this.sanitizeId(variant.id);
          const vSafeLabel = this.sanitizeLabel(variant.label || variant.id);
          lines.push(`        V_${vSafeId}[${vSafeLabel}]`);
        }
        lines.push("    end");
      } else {
        lines.push(`    P_${safeId}[${safeLabel}]`);
      }
    }

    // Render commodity nodes
    for (const node of commodityNodes) {
      const safeId = this.sanitizeId(node.id);
      const safeLabel = this.sanitizeLabel(node.label || node.id);
      lines.push(`    C_${safeId}((${safeLabel}))`);
    }

    // Build set of roles with subgraphs for edge targeting
    const rolesWithSubgraphs = new Set(roleToVariants.keys());

    // Render edges
    for (const edge of graph.edges) {
      const fromId = this.sanitizeId(edge.from);
      const toId = this.sanitizeId(edge.to);

      if (edge.kind === "input") {
        if (rolesWithSubgraphs.has(edge.to)) {
          lines.push(`    C_${fromId} --> ${toId}`);
        } else {
          lines.push(`    C_${fromId} --> P_${toId}`);
        }
      } else {
        if (rolesWithSubgraphs.has(edge.from)) {
          lines.push(`    ${fromId} --> C_${toId}`);
        } else {
          lines.push(`    P_${fromId} --> C_${toId}`);
        }
      }
    }

    lines.push("");
    lines.push("    classDef energy fill:#4a90d9,stroke:#2e5a87,color:#fff");
    lines.push("    classDef emission fill:#d94a4a,stroke:#872e2e,color:#fff");
    lines.push("    classDef demand fill:#4ad94a,stroke:#2e872e,color:#fff");
    lines.push("    classDef material fill:#d9a84a,stroke:#876a2e,color:#fff");
    lines.push("    classDef process fill:#9b59b6,stroke:#6c3483,color:#fff");
    lines.push("    classDef variant fill:#8e44ad,stroke:#5b2c6f,color:#fff");

    for (const node of graph.nodes) {
      const safeId = this.sanitizeId(node.id);
      if (node.kind === "commodity") {
        const commType = (node.type || "carrier").toLowerCase();
        if (commType === "env" || commType === "emission" || commType === "environment") {
          lines.push(`    class C_${safeId} emission`);
        } else if (commType === "dem" || commType === "demand" || commType === "service") {
          lines.push(`    class C_${safeId} demand`);
        } else if (commType === "mat" || commType === "material") {
          lines.push(`    class C_${safeId} material`);
        } else {
          lines.push(`    class C_${safeId} energy`);
        }
      } else if (node.type === "variant") {
        lines.push(`    class V_${safeId} variant`);
      } else if (!rolesWithSubgraphs.has(node.id)) {
        lines.push(`    class P_${safeId} process`);
      }
    }

    return lines.join("\n");
  }

  private sanitizeId(id: string): string {
    return id.replace(/[^a-zA-Z0-9_]/g, "_");
  }

  private sanitizeLabel(label: string): string {
    return label.replace(/["\[\](){}]/g, "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  private getWebviewContent(mermaidCode: string): string {
    const rolesActive = this.viewMode === "roles" ? "active" : "";
    const variantsActive = this.viewMode === "variants" ? "active" : "";

    return `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({
            startOnLoad: true,
            theme: 'dark',
            flowchart: {
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            }
        });

        const vscode = acquireVsCodeApi();

        function setViewMode(mode) {
            vscode.postMessage({ command: 'setViewMode', mode: mode });
        }
    </script>
    <style>
        body {
            background: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
            padding: 20px;
            margin: 0;
            font-family: var(--vscode-font-family);
        }
        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
        }
        h2 {
            color: var(--vscode-editor-foreground);
            margin: 0;
            font-weight: 400;
        }
        .view-toggle {
            display: flex;
            gap: 0;
            border: 1px solid var(--vscode-button-border, #444);
            border-radius: 4px;
            overflow: hidden;
        }
        .view-toggle button {
            background: var(--vscode-button-secondaryBackground, #3c3c3c);
            color: var(--vscode-button-secondaryForeground, #ccc);
            border: none;
            padding: 6px 12px;
            cursor: pointer;
            font-size: 12px;
            font-family: var(--vscode-font-family);
        }
        .view-toggle button:hover {
            background: var(--vscode-button-secondaryHoverBackground, #4c4c4c);
        }
        .view-toggle button.active {
            background: var(--vscode-button-background, #0e639c);
            color: var(--vscode-button-foreground, #fff);
        }
        .mermaid {
            text-align: center;
        }
        .legend {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-top: 20px;
            flex-wrap: wrap;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .legend-color {
            width: 20px;
            height: 20px;
            border-radius: 4px;
        }
        .energy { background: #4a90d9; }
        .emission { background: #d94a4a; }
        .demand { background: #4ad94a; }
        .material { background: #d9a84a; }
        .process { background: #9b59b6; }
        .variant { background: #8e44ad; }
    </style>
</head>
<body>
    <div class="header">
        <h2>Reference Energy System</h2>
        <div class="view-toggle">
            <button class="${rolesActive}" onclick="setViewMode('roles')">Roles</button>
            <button class="${variantsActive}" onclick="setViewMode('variants')">Variants</button>
        </div>
    </div>
    <div class="mermaid">
${mermaidCode}
    </div>
    <div class="legend">
        <div class="legend-item"><div class="legend-color energy"></div><span>Energy</span></div>
        <div class="legend-item"><div class="legend-color emission"></div><span>Emission</span></div>
        <div class="legend-item"><div class="legend-color demand"></div><span>Demand</span></div>
        <div class="legend-item"><div class="legend-color material"></div><span>Material</span></div>
        <div class="legend-item"><div class="legend-color process"></div><span>Process</span></div>
        <div class="legend-item"><div class="legend-color variant"></div><span>Variant</span></div>
    </div>
</body>
</html>`;
  }

  private getErrorContent(message: string): string {
    return `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {
            background: var(--vscode-editor-background);
            color: var(--vscode-errorForeground);
            padding: 20px;
            font-family: var(--vscode-font-family);
        }
        .error {
            padding: 20px;
            border: 1px solid var(--vscode-errorForeground);
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <div class="error">
        <h3>Error</h3>
        <p>${message}</p>
    </div>
</body>
</html>`;
  }

  public dispose(): void {
    ResPreviewPanel.currentPanel = undefined;

    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }

    this.panel.dispose();

    while (this.disposables.length) {
      const disposable = this.disposables.pop();
      if (disposable) {
        disposable.dispose();
      }
    }
  }
}
