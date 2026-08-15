"use client";

import { Fragment, useMemo } from "react";

import {
  normalizeJobDescription,
  type JobContentBlock,
  type JobInline,
} from "@/lib/job-description";

function InlineContent({ nodes }: { nodes: JobInline[] }) {
  return nodes.map((node, index) => {
    const key = `${node.type}-${index}`;
    if (node.type === "text") return <Fragment key={key}>{node.value}</Fragment>;
    if (node.type === "break") return <br key={key} />;
    if (node.type === "strong") return <strong key={key}><InlineContent nodes={node.children} /></strong>;
    if (node.type === "emphasis") return <em key={key}><InlineContent nodes={node.children} /></em>;
    return (
      <a key={key} href={node.href} target="_blank" rel="noopener noreferrer">
        <InlineContent nodes={node.children} />
      </a>
    );
  });
}

function ContentBlock({ block }: { block: JobContentBlock }) {
  if (block.type === "heading") {
    if (block.level === 2) return <h3><InlineContent nodes={block.children} /></h3>;
    if (block.level === 3) return <h4><InlineContent nodes={block.children} /></h4>;
    return <h5><InlineContent nodes={block.children} /></h5>;
  }
  if (block.type === "list") {
    const List = block.ordered ? "ol" : "ul";
    return <List>{block.items.map((item, index) => <li key={index}><InlineContent nodes={item} /></li>)}</List>;
  }
  return <p><InlineContent nodes={block.children} /></p>;
}

export function JobDescription({
  content,
  emptyText = "No description was published.",
}: {
  content: string;
  emptyText?: string;
}) {
  const normalized = useMemo(() => normalizeJobDescription(content), [content]);
  if (!normalized.blocks.length) return <p className="job-description-empty">{emptyText}</p>;
  return (
    <div className="job-description" data-source-type={normalized.sourceType}>
      {normalized.blocks.map((block, index) => <ContentBlock key={`${block.type}-${index}`} block={block} />)}
    </div>
  );
}
