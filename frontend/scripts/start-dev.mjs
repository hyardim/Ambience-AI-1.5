import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";

function run(command, args, { inherit = false } = {}) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    stdio: inherit ? "inherit" : "pipe",
  });
  if (result.error) {
    throw result.error;
  }
  return result;
}

function output(command, args) {
  const result = run(command, args);
  if (result.status !== 0) {
    return "";
  }
  return (result.stdout || "").trim();
}

function runOrExit(command, args) {
  const result = run(command, args, { inherit: true });
  process.exit(result.status ?? 1);
}

function runOrThrow(command, args) {
  const result = run(command, args, { inherit: true });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

if (existsSync("node_modules/esbuild/package.json")) {
  const jsVersion = output("node", [
    "-p",
    "require('./node_modules/esbuild/package.json').version",
  ]);
  let binVersion = output("node_modules/.bin/esbuild", ["--version"]);

  if (jsVersion && jsVersion !== binVersion) {
    console.log(
      `esbuild mismatch detected (js=${jsVersion}, binary=${binVersion || "missing"}), rebuilding...`,
    );
    runOrThrow("npm", ["rebuild", "esbuild", "--no-audit", "--no-fund"]);
    binVersion = output("node_modules/.bin/esbuild", ["--version"]);

    if (jsVersion !== binVersion) {
      console.log(
        `esbuild mismatch persists (js=${jsVersion}, binary=${binVersion || "missing"}), reinstalling esbuild@${jsVersion}...`,
      );
      runOrThrow("npm", [
        "install",
        "--no-save",
        "--no-audit",
        "--no-fund",
        `esbuild@${jsVersion}`,
      ]);
    }
  }
}

runOrExit("npm", ["run", "dev", "--", "--host"]);
