/**
 * ORANGE MCP Server — Obsidian Vault Tools
 * Инструменты: read_note, list_notes, write_note
 * Транспорт: StdioServerTransport (stdin/stdout)
 * Запуск: bun run index.ts
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "fs";
import { randomUUID } from "crypto";
import { dirname, extname, relative, resolve } from "path";
import { fileURLToPath } from "url";
import { VaultPathError, VaultPathResolver } from "./vault_paths.ts";

const PROJECT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const configuredVault = process.env.OBSIDIAN_VAULT_PATH || "examples/test_vault";
const VAULT_PATH = resolve(PROJECT_ROOT, configuredVault);
const MAX_NOTE_BYTES = 2 * 1024 * 1024;
const MAX_LIST_BYTES = 1024 * 1024;
let vaultResolver: VaultPathResolver | null = null;
let vaultError: VaultPathError | null = null;
try {
  vaultResolver = new VaultPathResolver(VAULT_PATH);
} catch (error) {
  vaultError = error instanceof VaultPathError
    ? error
    : new VaultPathError("Не удалось открыть vault", "NOT_CONFIGURED");
}

function resolveVaultPath(notePath: string): string {
  if (!vaultResolver) {
    throw vaultError || new VaultPathError("Vault не настроен", "NOT_CONFIGURED");
  }
  return vaultResolver.resolve(notePath);
}

function errorResult(error: unknown) {
  const safeError = error instanceof VaultPathError
    ? error
    : new VaultPathError("Операция с vault завершилась ошибкой");
  return {
    content: [{
      type: "text" as const,
      text: JSON.stringify({
        status: "error",
        error_code: safeError.code,
        message: safeError.message,
      }),
    }],
    isError: true,
  };
}

function writeNoteAtomic(fullPath: string, content: string): void {
  const tempPath = resolve(dirname(fullPath), `.${randomUUID()}.orange.tmp`);
  try {
    writeFileSync(tempPath, content, "utf-8");
    renameSync(tempPath, fullPath);
  } finally {
    rmSync(tempPath, { force: true });
  }
}

// Рекурсивный обход директории — возвращает все .md файлы
function getAllMarkdownFiles(dir: string, base: string = dir): string[] {
  const files: string[] = [];
  try {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const fullPath = resolve(dir, entry.name);
      const fileType = lstatSync(fullPath);
      if (fileType.isSymbolicLink()) {
        continue;
      }
      if (fileType.isDirectory() && !entry.name.startsWith(".")) {
        files.push(...getAllMarkdownFiles(fullPath, base));
      } else if (fileType.isFile() && extname(entry.name).toLowerCase() === ".md") {
        // Возвращаем относительный путь от корня vault
        files.push(relative(base, fullPath).replace(/\\/g, "/"));
      }
    }
  } catch (_error) {
    const relativeDirectory = relative(base, dir).replace(/\\/g, "/") || ".";
    throw new VaultPathError(
      `Не удалось полностью просканировать каталог vault: ${relativeDirectory}`,
    );
  }
  return files;
}

function boundedNoteList(files: string[]): string {
  if (!files.length) {
    return "Заметки не найдены.";
  }
  const selected: string[] = [];
  let bytes = 0;
  const truncatedMarker = "...[список обрезан по лимиту 1 MB]";
  const markerBytes = Buffer.byteLength(truncatedMarker, "utf-8") + 1;
  for (const file of files) {
    const lineBytes = Buffer.byteLength(file, "utf-8") + 1;
    if (bytes + lineBytes > MAX_LIST_BYTES) {
      while (selected.length && bytes + markerBytes > MAX_LIST_BYTES) {
        const removed = selected.pop() || "";
        bytes -= Buffer.byteLength(removed, "utf-8") + 1;
      }
      selected.push(truncatedMarker);
      break;
    }
    selected.push(file);
    bytes += lineBytes;
  }
  return selected.join("\n");
}

// Создаём MCP сервер
const server = new Server(
  { name: "orange-obsidian-mcp", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

// Список доступных инструментов
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "read_note",
      description: "Читает содержимое .md заметки из Obsidian vault по относительному пути",
      inputSchema: {
        type: "object",
        properties: {
          path: {
            type: "string",
            description: "Относительный путь к заметке внутри vault, например 'Projects/MyNote.md'",
          },
        },
        required: ["path"],
      },
    },
    {
      name: "list_notes",
      description: "Возвращает список всех .md файлов в Obsidian vault",
      inputSchema: {
        type: "object",
        properties: {},
      },
    },
    {
      name: "write_note",
      description: "Создаёт или полностью перезаписывает заметку в Obsidian vault",
      inputSchema: {
        type: "object",
        properties: {
          path: {
            type: "string",
            description: "Относительный путь к заметке, например 'Projects/NewNote.md'",
          },
          content: {
            type: "string",
            description: "Содержимое заметки в формате Markdown",
          },
        },
        required: ["path", "content"],
      },
    },
  ],
}));

// Обработчик вызовов инструментов
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  if (name === "list_notes") {
    if (!vaultResolver) {
      return errorResult(vaultError);
    }
    try {
      const files = getAllMarkdownFiles(vaultResolver.realRoot)
        .sort((a, b) => a.localeCompare(b));
      return {
        content: [
          {
            type: "text",
            text: boundedNoteList(files),
          },
        ],
      };
    } catch (error) {
      return errorResult(error);
    }
  }

  if (name === "read_note") {
    const notePath = args?.path as string;
    if (!notePath) {
      return errorResult(new VaultPathError("Путь заметки не указан"));
    }
    try {
      const fullPath = resolveVaultPath(notePath);
      if (extname(fullPath).toLowerCase() !== ".md") {
        throw new VaultPathError("Разрешены только .md заметки");
      }
      if (!existsSync(fullPath)) {
        throw new VaultPathError(`Файл не найден: ${notePath}`);
      }
      if (statSync(fullPath).size > MAX_NOTE_BYTES) {
        throw new VaultPathError("Заметка превышает лимит чтения 2 MB");
      }
      const content = readFileSync(fullPath, "utf-8");
      return { content: [{ type: "text", text: content }] };
    } catch (e) {
      return errorResult(e);
    }
  }

  if (name === "write_note") {
    const notePath = args?.path as string;
    const content = args?.content as string;
    if (!notePath || typeof content !== "string") {
      return errorResult(new VaultPathError("Путь или текст заметки не указаны"));
    }
    try {
      if (Buffer.byteLength(content, "utf-8") > MAX_NOTE_BYTES) {
        throw new VaultPathError("Заметка превышает лимит записи 2 MB");
      }
      const fullPath = resolveVaultPath(notePath);
      if (extname(fullPath).toLowerCase() !== ".md") {
        throw new VaultPathError("Разрешены только .md заметки");
      }
      mkdirSync(dirname(fullPath), { recursive: true });
      writeNoteAtomic(fullPath, content);
      return { content: [{ type: "text", text: `Записано: ${notePath}` }] };
    } catch (e) {
      return errorResult(e);
    }
  }

  return errorResult(
    new VaultPathError(`Неизвестный инструмент: ${String(name).slice(0, 80)}`),
  );
});

// Запуск сервера через stdio транспорт
const transport = new StdioServerTransport();
await server.connect(transport);
console.error(
  vaultResolver
    ? `[ORANGE MCP] Сервер запущен. Vault: ${vaultResolver.realRoot}`
    : `[ORANGE MCP] Сервер запущен без vault: ${vaultError?.message}`,
);
