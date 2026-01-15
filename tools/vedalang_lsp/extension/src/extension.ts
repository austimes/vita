import * as path from "path";
import * as fs from "fs";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

export async function activate(context: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration("vedalang");

  if (!config.get<boolean>("server.enabled", true)) {
    console.log("VedaLang language server is disabled");
    return;
  }

  const vedaRoot = findVedaDevtoolsRoot() || getWorkspaceRoot();
  const configuredPythonPath = config.get<string>("server.pythonPath", "");
  
  // Find the best Python to use
  const pythonPath = configuredPythonPath || findPythonPath(vedaRoot);
  
  if (!pythonPath) {
    vscode.window.showErrorMessage(
      "VedaLang: Could not find Python. Set vedalang.server.pythonPath in settings."
    );
    return;
  }

  console.log(`VedaLang: Using Python at ${pythonPath}`);
  console.log(`VedaLang: Working directory ${vedaRoot}`);
  
  // Show info message so user knows LSP is starting
  vscode.window.showInformationMessage(`VedaLang LSP starting with Python: ${pythonPath}`);

  // Server options - run Python with the server module
  // The server is in tools/vedalang_lsp/server/server.py
  const serverOptions: ServerOptions = {
    command: pythonPath,
    args: ["-m", "tools.vedalang_lsp.server.server"],
    options: {
      cwd: vedaRoot,
      env: {
        ...process.env,
        PYTHONPATH: vedaRoot,
      },
    },
  };
  
  console.log(`VedaLang: Server command: ${pythonPath} -m tools.vedalang_lsp.server.server`);

  // Client options
  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: "file", language: "vedalang" },
      { scheme: "file", pattern: "**/*.veda.yaml" },
    ],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.veda.yaml"),
    },
    outputChannelName: "VedaLang Language Server",
  };

  // Create the language client
  client = new LanguageClient(
    "vedalang",
    "VedaLang Language Server",
    serverOptions,
    clientOptions
  );

  // Start the client
  try {
    await client.start();
    console.log("VedaLang language server started");
  } catch (error) {
    console.error("Failed to start VedaLang language server:", error);
    vscode.window.showErrorMessage(
      `Failed to start VedaLang language server: ${error}`
    );
  }

  // Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand("vedalang.restartServer", async () => {
      if (client) {
        await client.stop();
        await client.start();
        vscode.window.showInformationMessage(
          "VedaLang language server restarted"
        );
      }
    })
  );
}

export async function deactivate(): Promise<void> {
  if (client) {
    await client.stop();
  }
}

function getWorkspaceRoot(): string {
  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length > 0) {
    return folders[0].uri.fsPath;
  }
  return process.cwd();
}

function findVedaDevtoolsRoot(): string | null {
  // Look for veda-devtools root by checking for pyproject.toml with vedalang
  const checkDir = (dir: string): boolean => {
    const pyproject = path.join(dir, "pyproject.toml");
    if (fs.existsSync(pyproject)) {
      const content = fs.readFileSync(pyproject, "utf8");
      return content.includes("vedalang");
    }
    return false;
  };

  // Check workspace folders first
  const folders = vscode.workspace.workspaceFolders;
  if (folders) {
    for (const folder of folders) {
      if (checkDir(folder.uri.fsPath)) {
        return folder.uri.fsPath;
      }
    }
  }

  // Walk up from extension path
  let current = path.dirname(path.dirname(path.dirname(__dirname)));
  for (let i = 0; i < 5; i++) {
    if (checkDir(current)) {
      return current;
    }
    current = path.dirname(current);
  }

  return null;
}

function findPythonPath(vedaRoot: string): string | null {
  // Try multiple locations for Python with pygls installed
  const candidates = [
    // uv/rye managed venv in project root
    path.join(vedaRoot, ".venv", "bin", "python"),
    // Parent directory venv (monorepo setup like /Users/gre538/code/.venv)
    path.join(path.dirname(vedaRoot), ".venv", "bin", "python"),
    // Common venv locations
    path.join(vedaRoot, "venv", "bin", "python"),
    path.join(vedaRoot, ".venv", "Scripts", "python.exe"), // Windows
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      console.log(`VedaLang: Found Python at ${candidate}`);
      return candidate;
    }
  }

  // Fall back to 'python' and hope it works
  console.log("VedaLang: No venv Python found, falling back to 'python'");
  return "python";
}
