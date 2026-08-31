'use client';

import Markdown from 'react-markdown';

export function MarkdownReport({ markdown, title }: { markdown: string; title: string }) {
  const exportPdf = () => window.print();
  const exportMd = () => {
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div>
      <div className="no-print mb-3 flex flex-wrap gap-2">
        <button className="ghost text-sm" onClick={exportPdf}>
          导出 PDF
        </button>
        <button className="ghost text-sm" onClick={exportMd}>
          导出 Markdown
        </button>
      </div>
      <article className="markdown-body sr-card p-5 md:p-7">
        <Markdown>{markdown}</Markdown>
      </article>
    </div>
  );
}
