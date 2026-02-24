import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";

interface ResGraph {
  nodes: unknown[];
  edges: unknown[];
  mermaid: string;
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

      if (!graph || !graph.mermaid) {
        this.panel.webview.html = this.getWebviewContent(
          "flowchart LR\n    N[No processes or commodities found]"
        );
        return;
      }

      this.panel.webview.html = this.getWebviewContent(graph.mermaid);
    } catch (error) {
      console.error("Failed to get RES graph:", error);
      this.panel.webview.html = this.getErrorContent(
        `Failed to generate RES graph: ${error}`
      );
    }
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
        /* Make Mermaid subgraph (stage) labels and borders visible in dark theme */
        .mermaid .cluster rect {
            stroke: rgba(255, 255, 255, 0.3) !important;
            stroke-width: 1.5px !important;
            fill: rgba(255, 255, 255, 0.04) !important;
        }
        .mermaid .cluster span,
        .mermaid .cluster text {
            color: rgba(255, 255, 255, 0.7) !important;
            fill: rgba(255, 255, 255, 0.7) !important;
            font-weight: 600 !important;
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
        .service { background: #4ad94a; }
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
        <div class="legend-item"><div class="legend-color service"></div><span>Service</span></div>
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
