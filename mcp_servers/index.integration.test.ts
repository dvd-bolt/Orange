import { afterEach, expect, test } from "bun:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "fs";
import { tmpdir } from "os";
import { join } from "path";

const roots: string[] = [];

function makeVault(): string {
  const root = mkdtempSync(join(tmpdir(), "orange-mcp-vault-"));
  roots.push(root);
  return root;
}

function inheritedEnvironment(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(process.env).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}

async function connect(vaultPath: string) {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: ["run", "index.ts"],
    cwd: import.meta.dir,
    env: {
      ...inheritedEnvironment(),
      OBSIDIAN_VAULT_PATH: vaultPath,
    },
    stderr: "pipe",
  });
  const client = new Client(
    { name: "orange-mcp-test", version: "1.0.0" },
    { capabilities: {} },
  );
  await client.connect(transport);
  return { client, transport };
}

function textResult(result: Awaited<ReturnType<Client["callTool"]>>): string {
  const content = result.content as
    | Array<{ type: string; text?: string }>
    | undefined;
  const item = content?.[0];
  return item?.type === "text" ? item.text || "" : "";
}

afterEach(() => {
  while (roots.length) {
    rmSync(roots.pop()!, { recursive: true, force: true });
  }
});

test("MCP list/read/write handles nested Unicode paths and duplicate names", async () => {
  const vault = makeVault();
  mkdirSync(join(vault, "one"), { recursive: true });
  mkdirSync(join(vault, "два"), { recursive: true });
  writeFileSync(join(vault, "one", "same.md"), "one", "utf-8");
  writeFileSync(join(vault, "два", "same.md"), "два", "utf-8");
  const { client, transport } = await connect(vault);

  try {
    const listed = textResult(await client.callTool({
      name: "list_notes",
      arguments: {},
    }));
    expect(listed).toContain("one/same.md");
    expect(listed).toContain("два/same.md");

    const read = textResult(await client.callTool({
      name: "read_note",
      arguments: { path: "два/same.md" },
    }));
    expect(read).toBe("два");

    const written = await client.callTool({
      name: "write_note",
      arguments: { path: "Проекты/План.md", content: "# План" },
    });
    expect(written.isError).not.toBe(true);
    expect(readFileSync(join(vault, "Проекты", "План.md"), "utf-8")).toBe(
      "# План",
    );
  } finally {
    await client.close();
    await transport.close();
  }
});

test("MCP rejects traversal and symlink paths", async () => {
  const vault = makeVault();
  const outside = mkdtempSync(join(tmpdir(), "orange-mcp-outside-"));
  roots.push(outside);
  writeFileSync(join(outside, "secret.md"), "secret", "utf-8");
  symlinkSync(join(outside, "secret.md"), join(vault, "linked.md"));
  const { client, transport } = await connect(vault);

  try {
    for (const request of [
      { name: "read_note", arguments: { path: "../secret.md" } },
      {
        name: "write_note",
        arguments: { path: "../../x.md", content: "x" },
      },
      { name: "read_note", arguments: { path: "linked.md" } },
    ]) {
      const result = await client.callTool(request);
      expect(result.isError).toBe(true);
      expect(textResult(result)).toContain('"status":"error"');
    }
    expect(() => readFileSync(join(vault, "x.md"), "utf-8")).toThrow();
  } finally {
    await client.close();
    await transport.close();
  }
});
