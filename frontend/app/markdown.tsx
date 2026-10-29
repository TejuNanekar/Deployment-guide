"use client";

import { ReactNode, useState } from "react";

type Block =
  | { kind: "h"; level: 1 | 2 | 3; text: string }
  | { kind: "p"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "code"; lang: string; text: string }
  | { kind: "hr" };

export function FormattedAnswer({ text }: { text: string }) {
  const blocks = parseBlocks(text);
  return (
    <div className="answer">
      {blocks.map((block, index) => renderBlock(block, index))}
    </div>
  );
}

function renderBlock(block: Block, index: number) {
  if (block.kind === "h") {
    const Tag = block.level === 1 ? "h2" : "h3";
    return (
      <Tag key={index} className={block.level === 1 ? "answer-title" : "answer-step"}>
        {inline(block.text)}
      </Tag>
    );
  }
  if (block.kind === "code") return <CodeBlock key={index} lang={block.lang} text={block.text} />;
  if (block.kind === "ul") {
    return (
      <ul key={index} className="answer-list">
        {block.items.map((item, itemIndex) => (
          <li key={itemIndex}>{inline(item)}</li>
        ))}
      </ul>
    );
  }
  if (block.kind === "ol") {
    return (
      <ol key={index} className="answer-list">
        {block.items.map((item, itemIndex) => (
          <li key={itemIndex}>{inline(item)}</li>
        ))}
      </ol>
    );
  }
  if (block.kind === "hr") return <hr key={index} />;
  const label = labelOf(block.text);
  return (
    <p key={index} className={label ? `fact ${label}` : undefined}>
      {inline(block.text)}
    </p>
  );
}

function CodeBlock({ lang, text }: { lang: string; text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="codeblock">
      <div className="codebar">
        <span>{lang || "command"}</span>
        <button
          type="button"
          className="ghost"
          onClick={() => {
            void navigator.clipboard.writeText(text).then(() => {
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1500);
            });
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre>{text}</pre>
    </div>
  );
}

function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const fence = line.match(/^\s*```([\w-]*)\s*$/);
    if (fence) {
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) {
        body.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ kind: "code", lang: fence[1] || "", text: dedent(body) });
      continue;
    }
    if (!line.trim() || /^---+$/.test(line.trim())) {
      if (/^---+$/.test(line.trim())) blocks.push({ kind: "hr" });
      index += 1;
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length as 1 | 2 | 3;
      blocks.push({ kind: "h", level, text: heading[2].trim() });
      index += 1;
      continue;
    }
    if (isStepTitle(line)) {
      const numbered = line.match(/^(\s*)(\d+)\.\s+(.+)$/);
      if (numbered) {
        blocks.push({
          kind: "h",
          level: numbered[1].length >= 2 ? 3 : 2,
          text: `${numbered[2]}. ${numbered[3].trim()}`,
        });
        index += 1;
        continue;
      }
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, "").trim());
        index += 1;
      }
      blocks.push({ kind: "ul", items });
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index]) && !isStepTitle(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+\.\s+/, "").trim());
        index += 1;
      }
      if (items.length > 0) {
        blocks.push({ kind: "ol", items });
        continue;
      }
    }
    const paragraph: string[] = [];
    while (index < lines.length && lines[index].trim() && !isBoundary(lines[index])) {
      if (paragraph.length > 0 && isFactLine(lines[index])) break;
      paragraph.push(lines[index].trim());
      index += 1;
    }
    for (const part of splitFacts(paragraph.join(" "))) blocks.push({ kind: "p", text: part });
  }
  return blocks;
}

function isBoundary(line: string): boolean {
  return /^\s*```/.test(line) || /^#{1,3}\s+/.test(line) || /^\s*[-*]\s+/.test(line) || isStepTitle(line) || /^\s*\d+\.\s+/.test(line);
}

function isStepTitle(line: string): boolean {
  const match = line.match(/^\s*\d+\.\s+(\*\*[^*]+\*\*)\s*$/);
  return !!match && match[1].length <= 80;
}

function dedent(lines: string[]): string {
  const indents = lines.filter((line) => line.trim()).map((line) => line.match(/^ */)?.[0].length ?? 0);
  const trim = indents.length > 0 ? Math.min(...indents) : 0;
  return lines.map((line) => line.slice(trim)).join("\n").trim();
}

function isFactLine(line: string): boolean {
  return /^\s*\*\*(Why|Where|Done when):\*\*/i.test(line);
}

function splitFacts(text: string): string[] {
  return text
    .split(/(?=\*\*(?:Why|Where|Done when):\*\*)/i)
    .map((part) => part.trim())
    .filter(Boolean);
}

function labelOf(text: string): "why" | "where" | "done" | null {
  const plain = text.replace(/\*/g, "").trim().toLowerCase();
  if (plain.startsWith("why:")) return "why";
  if (plain.startsWith("where:")) return "where";
  if (plain.startsWith("done when:")) return "done";
  return null;
}

function inline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*|<https?:\/\/[^>\s]+>)/g;
  let last = 0;
  let key = 0;
  for (const match of text.matchAll(pattern)) {
    const token = match[0];
    const start = match.index ?? 0;
    if (start > last) nodes.push(text.slice(last, start));
    if (token.startsWith("**")) nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith("`")) nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    else if (token.startsWith("<")) {
      const url = token.slice(1, -1);
      nodes.push(
        <a key={key} href={url} target="_blank" rel="noreferrer">
          {url}
        </a>,
      );
    } else nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    key += 1;
    last = start + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}
