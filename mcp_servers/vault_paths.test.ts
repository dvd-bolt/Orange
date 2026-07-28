import { afterEach, describe, expect, test } from "bun:test";
import {
  mkdirSync,
  mkdtempSync,
  realpathSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "fs";
import { tmpdir } from "os";
import { join } from "path";

import { VaultPathError, VaultPathResolver } from "./vault_paths.ts";

const roots: string[] = [];

function makeRoot(prefix: string): string {
  const root = mkdtempSync(join(tmpdir(), prefix));
  roots.push(root);
  return root;
}

afterEach(() => {
  while (roots.length) {
    rmSync(roots.pop()!, { recursive: true, force: true });
  }
});

describe("VaultPathResolver", () => {
  test("supports nested Unicode paths", () => {
    const vault = makeRoot("orange-vault-");
    mkdirSync(join(vault, "Проекты"), { recursive: true });
    writeFileSync(join(vault, "Проекты", "План.md"), "# План", "utf-8");

    const resolver = new VaultPathResolver(vault);
    expect(resolver.resolve("Проекты/План.md")).toBe(
      join(realpathSync(vault), "Проекты", "План.md"),
    );
  });

  test("rejects traversal and absolute paths", () => {
    const vault = makeRoot("orange-vault-");
    const resolver = new VaultPathResolver(vault);

    expect(() => resolver.resolve("../secret.md")).toThrow(VaultPathError);
    expect(() => resolver.resolve(join(tmpdir(), "secret.md"))).toThrow(
      VaultPathError,
    );
    expect(() => resolver.resolve(`${"a".repeat(1001)}.md`)).toThrow(
      VaultPathError,
    );
  });

  test("rejects file and directory symlinks", () => {
    const vault = makeRoot("orange-vault-");
    const outside = makeRoot("orange-outside-");
    writeFileSync(join(outside, "secret.md"), "secret", "utf-8");
    symlinkSync(join(outside, "secret.md"), join(vault, "file-link.md"));
    symlinkSync(outside, join(vault, "dir-link"), "dir");
    const resolver = new VaultPathResolver(vault);

    expect(() => resolver.resolve("file-link.md")).toThrow(VaultPathError);
    expect(() => resolver.resolve("dir-link/secret.md")).toThrow(
      VaultPathError,
    );
  });

  test("reports a missing vault as not configured", () => {
    const parent = makeRoot("orange-missing-");
    try {
      new VaultPathResolver(join(parent, "does-not-exist"));
      throw new Error("resolver unexpectedly accepted a missing vault");
    } catch (error) {
      expect(error).toBeInstanceOf(VaultPathError);
      expect((error as VaultPathError).code).toBe("NOT_CONFIGURED");
    }
  });
});
