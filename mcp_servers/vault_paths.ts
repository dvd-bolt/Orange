import {
  existsSync,
  lstatSync,
  realpathSync,
} from "fs";
import {
  isAbsolute,
  relative,
  resolve,
  sep,
} from "path";

export class VaultPathError extends Error {
  readonly code: "NOT_CONFIGURED" | "VALIDATION_ERROR";

  constructor(
    message: string,
    code: "NOT_CONFIGURED" | "VALIDATION_ERROR" = "VALIDATION_ERROR",
  ) {
    super(message);
    this.name = "VaultPathError";
    this.code = code;
  }
}

function isInside(root: string, candidate: string): boolean {
  const rel = relative(root, candidate);
  return rel === "" || (!rel.startsWith(`..${sep}`) && rel !== ".." && !isAbsolute(rel));
}

function assertNoSymlinkComponents(root: string, candidate: string): void {
  const rel = relative(root, candidate);
  if (!rel || rel === ".") {
    return;
  }

  let current = root;
  for (const part of rel.split(/[\\/]/)) {
    current = resolve(current, part);
    if (!existsSync(current)) {
      break;
    }
    if (lstatSync(current).isSymbolicLink()) {
      throw new VaultPathError("Ссылки внутри vault запрещены");
    }
  }
}

export class VaultPathResolver {
  readonly root: string;
  readonly realRoot: string;

  constructor(vaultPath: string) {
    this.root = resolve(vaultPath);
    if (!existsSync(this.root)) {
      throw new VaultPathError(
        "Vault не настроен или недоступен",
        "NOT_CONFIGURED",
      );
    }
    if (!lstatSync(this.root).isDirectory()) {
      throw new VaultPathError(
        "Настроенный vault не является каталогом",
        "NOT_CONFIGURED",
      );
    }
    this.realRoot = realpathSync(this.root);
  }

  resolve(notePath: string): string {
    if (
      typeof notePath !== "string"
      || !notePath.trim()
      || notePath.length > 1_000
      || notePath.includes("\0")
      || isAbsolute(notePath)
    ) {
      throw new VaultPathError("Нужен относительный путь внутри vault");
    }

    const candidate = resolve(this.realRoot, notePath);
    if (!isInside(this.realRoot, candidate)) {
      throw new VaultPathError("Путь выходит за пределы vault");
    }

    assertNoSymlinkComponents(this.realRoot, candidate);

    let existingAncestor = candidate;
    while (!existsSync(existingAncestor) && existingAncestor !== this.realRoot) {
      existingAncestor = resolve(existingAncestor, "..");
    }
    const realAncestor = realpathSync(existingAncestor);
    if (!isInside(this.realRoot, realAncestor)) {
      throw new VaultPathError("Путь выходит за пределы vault через ссылку");
    }
    return candidate;
  }
}
