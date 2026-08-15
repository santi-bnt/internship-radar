export type JobInline =
  | { type: "text"; value: string }
  | { type: "strong"; children: JobInline[] }
  | { type: "emphasis"; children: JobInline[] }
  | { type: "link"; href: string; children: JobInline[] }
  | { type: "break" };

export type JobContentBlock =
  | { type: "heading"; level: 2 | 3 | 4; children: JobInline[] }
  | { type: "paragraph"; children: JobInline[] }
  | { type: "list"; ordered: boolean; items: JobInline[][] };

export type NormalizedJobContent = {
  blocks: JobContentBlock[];
  sourceType: "html" | "markdown" | "text";
};

const BLOCK_TAGS = new Set([
  "ARTICLE", "DIV", "H1", "H2", "H3", "H4", "H5", "H6",
  "OL", "P", "SECTION", "UL",
]);
const IGNORED_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "SVG", "IFRAME"]);

function compactText(value: string): string {
  return value.replace(/\u00a0/g, " ").replace(/[ \t]+/g, " ").trim();
}

function inlineText(value: string): string {
  return value.replace(/\u00a0/g, " ").replace(/\s+/g, " ");
}

function safeHref(value: string | null): string | null {
  if (!value) return null;
  if (value.startsWith("/")) return value;
  try {
    const base = typeof window === "undefined" ? "https://localhost.invalid" : window.location.origin;
    const url = new URL(value, base);
    return ["http:", "https:", "mailto:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function parseInlineNode(node: Node): JobInline[] {
  if (node.nodeType === Node.TEXT_NODE) {
    const value = inlineText(node.textContent ?? "");
    return value.trim() ? [{ type: "text", value }] : [];
  }
  if (!(node instanceof HTMLElement) || IGNORED_TAGS.has(node.tagName)) return [];
  if (node.tagName === "BR") return [{ type: "break" }];

  const children = Array.from(node.childNodes).flatMap(parseInlineNode);
  if (!children.length) return [];
  if (node.matches("strong, b")) return [{ type: "strong", children }];
  if (node.matches("em, i")) return [{ type: "emphasis", children }];
  if (node.tagName === "A") {
    const href = safeHref(node.getAttribute("href"));
    return href ? [{ type: "link", href, children }] : children;
  }
  return children;
}

function hasDirectBlockChildren(element: HTMLElement): boolean {
  return Array.from(element.children).some((child) => BLOCK_TAGS.has(child.tagName));
}

function parseHtmlElement(element: HTMLElement): JobContentBlock[] {
  if (IGNORED_TAGS.has(element.tagName)) return [];
  if (/^H[1-6]$/.test(element.tagName)) {
    const numericLevel = Number(element.tagName.slice(1));
    const level = Math.min(4, Math.max(2, numericLevel + 1)) as 2 | 3 | 4;
    const children = parseInlineNode(element);
    return children.length ? [{ type: "heading", level, children }] : [];
  }
  if (element.matches("ul, ol")) {
    const items = Array.from(element.children)
      .filter((child) => child.tagName === "LI")
      .map((child) => parseInlineNode(child))
      .filter((item) => item.length);
    return items.length
      ? [{ type: "list", ordered: element.tagName === "OL", items }]
      : [];
  }
  if (element.matches("div, section, article") && hasDirectBlockChildren(element)) {
    return Array.from(element.childNodes).flatMap((child) => {
      if (child instanceof HTMLElement) return parseHtmlElement(child);
      const value = compactText(child.textContent ?? "");
      return value
        ? [{ type: "paragraph", children: [{ type: "text", value }] } as JobContentBlock]
        : [];
    });
  }

  const children = parseInlineNode(element);
  return children.length ? [{ type: "paragraph", children }] : [];
}

function decodeEntities(value: string): string {
  if (typeof document === "undefined") return value;
  let decoded = value;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const textarea = document.createElement("textarea");
    textarea.innerHTML = decoded;
    const next = textarea.value;
    if (next === decoded) break;
    decoded = next;
  }
  return decoded;
}

function parseMarkdownInline(value: string): JobInline[] {
  const output: JobInline[] = [];
  const tokenPattern = /(\*\*[^*]+\*\*|\[[^\]]+\]\((?:https?:\/\/|mailto:)[^)]+\))/g;
  let cursor = 0;
  for (const match of value.matchAll(tokenPattern)) {
    const index = match.index ?? 0;
    const before = inlineText(value.slice(cursor, index));
    if (before.trim()) output.push({ type: "text", value: before });
    const token = match[0];
    if (token.startsWith("**")) {
      output.push({
        type: "strong",
        children: [{ type: "text", value: compactText(token.slice(2, -2)) }],
      });
    } else {
      const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      const href = link ? safeHref(link[2]) : null;
      if (link && href) {
        output.push({ type: "link", href, children: [{ type: "text", value: link[1] }] });
      }
    }
    cursor = index + token.length;
  }
  const remainder = inlineText(value.slice(cursor));
  if (remainder.trim()) output.push({ type: "text", value: remainder });
  return output;
}

function parseTextOrMarkdown(value: string): NormalizedJobContent {
  const lines = value.replace(/\r\n?/g, "\n").split("\n");
  const blocks: JobContentBlock[] = [];
  let paragraph: string[] = [];
  let listItems: JobInline[][] = [];
  let ordered = false;
  let markdownDetected = false;

  const flushParagraph = () => {
    const text = compactText(paragraph.join(" "));
    if (text) blocks.push({ type: "paragraph", children: parseMarkdownInline(text) });
    paragraph = [];
  };
  const flushList = () => {
    if (listItems.length) blocks.push({ type: "list", ordered, items: listItems });
    listItems = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    const bullet = line.match(/^[-*•]\s+(.+)$/);
    const numbered = line.match(/^\d+[.)]\s+(.+)$/);
    if (heading) {
      markdownDetected = true;
      flushParagraph();
      flushList();
      blocks.push({
        type: "heading",
        level: Math.min(4, Math.max(2, heading[1].length + 1)) as 2 | 3 | 4,
        children: parseMarkdownInline(heading[2]),
      });
    } else if (bullet || numbered) {
      markdownDetected = true;
      flushParagraph();
      const nextOrdered = Boolean(numbered);
      if (listItems.length && ordered !== nextOrdered) flushList();
      ordered = nextOrdered;
      listItems.push(parseMarkdownInline((bullet ?? numbered)?.[1] ?? ""));
    } else {
      flushList();
      paragraph.push(line);
      if (/\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)/.test(line)) markdownDetected = true;
    }
  }
  flushParagraph();
  flushList();
  return { blocks, sourceType: markdownDetected ? "markdown" : "text" };
}

export function normalizeJobDescription(content: string): NormalizedJobContent {
  const decoded = decodeEntities(content ?? "").trim();
  if (!decoded) return { blocks: [], sourceType: "text" };
  const containsHtml = /<\/?[a-z][^>]*>/i.test(decoded);
  if (!containsHtml || typeof DOMParser === "undefined") return parseTextOrMarkdown(decoded);

  const documentNode = new DOMParser().parseFromString(decoded, "text/html");
  const blocks = Array.from(documentNode.body.childNodes).flatMap((node) => {
    if (node instanceof HTMLElement) return parseHtmlElement(node);
    const value = compactText(node.textContent ?? "");
    return value
      ? [{ type: "paragraph", children: [{ type: "text", value }] } as JobContentBlock]
      : [];
  });
  return { blocks, sourceType: "html" };
}
