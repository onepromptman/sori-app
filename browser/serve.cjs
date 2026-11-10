const { createServer } = require("node:http");
const { readFile } = require("node:fs/promises");
const { extname, join } = require("node:path");

const host = "127.0.0.1";
const port = 17841;
const site = join(__dirname, "site");
const types = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".png": "image/png",
  ".txt": "text/plain; charset=utf-8",
  ".woff2": "font/woff2",
};

const server = createServer(async (request, response) => {
  if (request.method !== "GET" && request.method !== "HEAD") {
    response.writeHead(405, { Allow: "GET, HEAD" }).end();
    return;
  }

  const pathname = request.url.split("?")[0];
  const name = pathname === "/" ? "index.html" : pathname.slice(1);
  const type = types[extname(name)];
  if (!type || !/^\/[a-zA-Z0-9_.\/-]*$/.test(pathname) || name.split("/").includes("..")) {
    response.writeHead(404).end();
    return;
  }

  try {
    const data = await readFile(join(site, name));
    response.writeHead(200, { "Content-Type": type, "Content-Length": data.length });
    response.end(request.method === "HEAD" ? undefined : data);
  } catch {
    response.writeHead(404).end();
  }
});

server.on("error", (error) => {
  console.error(`Sori could not start at http://${host}:${port}/ (${error.code}).`);
  process.exitCode = 1;
});
server.listen(port, host, () => console.log(`Open Sori at http://${host}:${port}/`));
