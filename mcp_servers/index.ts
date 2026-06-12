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
import { readFileSync, readdirSync, writeFileSync, existsSync, mkdirSync } from "fs";
import { join, extname, dirname } from "path";

// Путь к Obsidian Vault (берём из .env или fallback к test_vault)
const VAULT_PATH = process.env.OBSIDIAN_VAULT_PATH || "./test_vault";

// Рекурсивный обход директории — возвращает все .md файлы
function getAllMarkdownFiles(dir: string, base: string = dir): string[] {
  const files: string[] = [];
  try {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const fullPath = join(dir, entry.name);
      if (entry.isDirectory() && !entry.name.startsWith(".")) {
        files.push(...getAllMarkdownFiles(fullPath, base));
      } else if (entry.isFile() && extname(entry.name) === ".md") {
        // Возвращаем относительный путь от корня vault
        files.push(fullPath.replace(base + "/", "").replace(base + "\\", ""));
      }
    }
  } catch (e) {
    // Игнорируем директории без доступа
  }
  return files;
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
    const files = getAllMarkdownFiles(VAULT_PATH);
    return {
      content: [
        {
          type: "text",
          text: files.length > 0 ? files.join("\n") : "Заметки не найдены.",
        },
      ],
    };
  }

  if (name === "read_note") {
    const notePath = args?.path as string;
    if (!notePath) {
      return { content: [{ type: "text", text: "Ошибка: путь не указан" }], isError: true };
    }
    // Path traversal защита: запрещаем выход за пределы vault
    const fullPath = join(VAULT_PATH, notePath);
    if (!fullPath.startsWith(VAULT_PATH)) {
      return { content: [{ type: "text", text: "Ошибка: запрещённый путь" }], isError: true };
    }
    if (!existsSync(fullPath)) {
      return { content: [{ type: "text", text: `Файл не найден: ${notePath}` }], isError: true };
    }
    try {
      const content = readFileSync(fullPath, "utf-8");
      return { content: [{ type: "text", text: content }] };
    } catch (e) {
      return { content: [{ type: "text", text: `Ошибка чтения: ${e}` }], isError: true };
    }
  }

  if (name === "write_note") {
    const notePath = args?.path as string;
    const content = args?.content as string;
    if (!notePath || content === undefined) {
      return { content: [{ type: "text", text: "Ошибка: путь или содержимое не указаны" }], isError: true };
    }
    const fullPath = join(VAULT_PATH, notePath);
    // Path traversal защита
    if (!fullPath.startsWith(VAULT_PATH)) {
      return { content: [{ type: "text", text: "Ошибка: запрещённый путь" }], isError: true };
    }
    try {
      // Создаём директории если не существуют
      mkdirSync(dirname(fullPath), { recursive: true });
      writeFileSync(fullPath, content, "utf-8");
      return { content: [{ type: "text", text: `Записано: ${notePath}` }] };
    } catch (e) {
      return { content: [{ type: "text", text: `Ошибка записи: ${e}` }], isError: true };
    }
  }

  throw new Error(`Неизвестный инструмент: ${name}`);
});

// Запуск сервера через stdio транспорт
const transport = new StdioServerTransport();
await server.connect(transport);
console.error(`[ORANGE MCP] Сервер запущен. Vault: ${VAULT_PATH}`);