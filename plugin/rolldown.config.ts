import { exec } from "node:child_process";
import path from "node:path";
import url from "node:url";
import { defineConfig } from "rolldown";

const isWatching = !!process.env.ROLLUP_WATCH;
const sdPlugin = "com.bgstreamboy.companion";
const sdPluginFolder = `${sdPlugin}.sdPlugin`;

export default defineConfig({
  input: "src/plugin.ts",
  output: {
    file: `${sdPluginFolder}/bin/plugin.js`,
    sourcemap: isWatching,
    sourcemapPathTransform: (relativeSourcePath, sourcemapPath) =>
      url.pathToFileURL(path.resolve(path.dirname(sourcemapPath), relativeSourcePath)).href,
    minify: !isWatching,
  },
  transform: {
    decorator: { legacy: true },
  },
  platform: "node",
  resolve: {
    conditionNames: ["node"],
  },
  // @napi-rs/canvas ships native .node binaries that can't be bundled.
  // Resolved from the .sdPlugin's own node_modules at runtime.
  external: [/^@napi-rs\/canvas/],
  plugins: [
    {
      name: "watch-externals",
      buildStart() {
        this.addWatchFile(`${sdPluginFolder}/manifest.json`);
      },
      buildEnd() {
        if (isWatching) {
          exec(`streamdeck restart ${sdPlugin}`, (error, stdout, stderr) => {
            if (stdout) console.log(stdout.trim());
            if (stderr) console.error(stderr.trim());
            if (error) console.error("Failed to restart Stream Deck:", error.message);
          });
        }
      },
    },
    {
      name: "emit-module-package-file",
      generateBundle() {
        this.emitFile({ fileName: "package.json", source: `{ "type": "module" }`, type: "asset" });
      },
    },
  ],
});
