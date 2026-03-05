import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";

interface ResGraphResponse {
  graph?: {
    nodes?: unknown[];
    edges?: unknown[];
  };
  mermaid?: string;
  facets?: {
    regions?: string[];
  };
  diagnostics?: unknown[];
}

type SourceMode = "source" | "compiled";
type Granularity =
  | "role"
  | "provider"
  | "provider_variant"
  | "provider_variant_mode"
  | "instance"
  | "variant";
type CommodityView = "collapse_scope" | "scoped";

export class ResPreviewPanel {
  public static currentPanel: ResPreviewPanel | undefined;
  private static readonly viewType = "vedalangResPreview";

  private readonly panel: vscode.WebviewPanel;
  private readonly client: LanguageClient;
  private readonly extensionUri: vscode.Uri;
  private disposables: vscode.Disposable[] = [];
  private debounceTimer: NodeJS.Timeout | undefined;
  private lastVedaDocument: vscode.TextDocument | undefined;

  private mode: SourceMode = "source";
  private granularity: Granularity = "role";
  private commodityView: CommodityView = "collapse_scope";
  private selectedRegions: string[] = [];

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

    const editor = vscode.window.activeTextEditor;
    if (editor && this.isVedaDocument(editor.document)) {
      this.lastVedaDocument = editor.document;
    }

    this.updateContent();

    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

    this.panel.webview.onDidReceiveMessage(
      (message) => {
        if (message.command === "setMode") {
          this.mode = message.mode as SourceMode;
          this.updateContent();
        } else if (message.command === "setGranularity") {
          this.granularity = message.granularity as Granularity;
          this.updateContent();
        } else if (message.command === "setCommodityView") {
          this.commodityView = message.commodityView as CommodityView;
          this.updateContent();
        } else if (message.command === "setRegions") {
          const raw = String(message.regions || "");
          this.selectedRegions = raw
            .split(",")
            .map((v: string) => v.trim())
            .filter((v: string) => v.length > 0);
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
    let doc = this.lastVedaDocument;
    const editor = vscode.window.activeTextEditor;
    if (editor && this.isVedaDocument(editor.document)) {
      doc = editor.document;
      this.lastVedaDocument = doc;
    }

    if (!doc) {
      this.panel.webview.html = this.getWebviewContent(
        "flowchart LR\n    N[No VedaLang file open]",
        [],
        []
      );
      return;
    }

    try {
      const graph = await this.client.sendRequest<ResGraphResponse>(
        "veda/resGraph",
        {
          textDocument: {
            uri: doc.uri.toString(),
          },
          mode: this.mode,
          granularity: this.granularity,
          commodityView: this.commodityView,
          lens: "system",
          regions: this.selectedRegions,
          includeVariants:
            this.granularity === "variant" ||
            this.granularity === "provider_variant",
        }
      );

      if (!graph || !graph.mermaid) {
        this.panel.webview.html = this.getWebviewContent(
          "flowchart LR\n    N[No processes or commodities found]",
          [],
          []
        );
        return;
      }

      const regions = graph.facets?.regions || [];
      const diagnostics = (graph.diagnostics || []) as unknown[];
      this.panel.webview.html = this.getWebviewContent(
        graph.mermaid,
        regions,
        diagnostics
      );
    } catch (error) {
      console.error("Failed to get RES graph:", error);
      this.panel.webview.html = this.getErrorContent(
        `Failed to generate RES graph: ${error}`
      );
    }
  }

  private getWebviewContent(
    mermaidCode: string,
    regions: string[],
    diagnostics: unknown[]
  ): string {
    const modeSourceSelected = this.mode === "source" ? "selected" : "";
    const modeCompiledSelected = this.mode === "compiled" ? "selected" : "";
    const roleSelected = this.granularity === "role" ? "selected" : "";
    const providerSelected = this.granularity === "provider" ? "selected" : "";
    const variantSelected =
      this.granularity === "provider_variant" || this.granularity === "variant"
        ? "selected"
        : "";
    const modeSelected =
      this.granularity === "provider_variant_mode" ? "selected" : "";
    const instanceSelected = this.granularity === "instance" ? "selected" : "";
    const collapseScopeSelected =
      this.commodityView === "collapse_scope" ? "selected" : "";
    const scopedSelected = this.commodityView === "scoped" ? "selected" : "";
    const regionCsv = this.selectedRegions.join(",");
    const regionHint = regions.join(", ");
    const diagnosticsText = JSON.stringify(diagnostics, null, 2).replace(/</g, "&lt;");

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

        function setMode(value) {
            vscode.postMessage({ command: 'setMode', mode: value });
        }

        function setGranularity(value) {
            vscode.postMessage({ command: 'setGranularity', granularity: value });
        }

        function setCommodityView(value) {
            vscode.postMessage({ command: 'setCommodityView', commodityView: value });
        }

        function setRegions(value) {
            vscode.postMessage({ command: 'setRegions', regions: value });
        }
    </script>
    <style>
        body {
            background: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
            padding: 16px;
            margin: 0;
            font-family: var(--vscode-font-family);
        }
        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
            gap: 8px;
        }
        .controls {
            display: grid;
            grid-template-columns: repeat(4, minmax(140px, 1fr));
            gap: 8px;
            margin-bottom: 12px;
        }
        .control {
            display: flex;
            flex-direction: column;
            gap: 4px;
            font-size: 12px;
        }
        select, input {
            background: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border);
            border-radius: 4px;
            padding: 4px 6px;
            font-family: var(--vscode-font-family);
            font-size: 12px;
        }
        .meta {
            margin-bottom: 8px;
            font-size: 11px;
            opacity: 0.8;
        }
        .mermaid {
            text-align: center;
            border-top: 1px solid rgba(255,255,255,0.15);
            padding-top: 12px;
        }
        .diag {
            margin-top: 12px;
            font-size: 11px;
            white-space: pre-wrap;
            border-top: 1px solid rgba(255,255,255,0.15);
            padding-top: 8px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h2>Reference Energy System</h2>
    </div>
    <div class="controls">
        <label class="control">Mode
            <select onchange="setMode(this.value)">
              <option value="source" ${modeSourceSelected}>source</option>
              <option value="compiled" ${modeCompiledSelected}>compiled</option>
            </select>
        </label>
        <label class="control">Granularity
            <select onchange="setGranularity(this.value)">
              <option value="role" ${roleSelected}>role</option>
              <option value="provider" ${providerSelected}>provider</option>
              <option value="provider_variant" ${variantSelected}>provider×variant</option>
              <option value="provider_variant_mode" ${modeSelected}>provider×variant×mode</option>
              <option value="instance" ${instanceSelected}>instance</option>
            </select>
        </label>
        <label class="control">Commodity view
            <select onchange="setCommodityView(this.value)">
              <option value="collapse_scope" ${collapseScopeSelected}>collapse scope</option>
              <option value="scoped" ${scopedSelected}>scoped</option>
            </select>
        </label>
        <label class="control">Regions (CSV)
            <input value="${regionCsv}" placeholder="${regionHint}" onchange="setRegions(this.value)" />
        </label>
    </div>
    <div class="meta">Available regions: ${regionHint || "(none)"}</div>
    <div class="mermaid">
${mermaidCode}
    </div>
    <div class="diag">Diagnostics:\n${diagnosticsText}</div>
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
