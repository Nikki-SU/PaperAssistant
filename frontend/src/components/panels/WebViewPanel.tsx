/**
 * 内嵌 WebView 面板（SPEC §六：搜索网站 - 用户可自定义）。
 *
 * 用 iframe 实现。Tauri v2 默认允许同源/任意源 iframe。
 * 提供常用预设：Google Scholar / arXiv / Web of Science / PubMed。
 * 用户可自由输入 URL。
 */
import { useState } from "react";

const PRESETS: { label: string; url: string }[] = [
  { label: "Google Scholar", url: "https://scholar.google.com/" },
  { label: "arXiv",           url: "https://arxiv.org/" },
  { label: "Web of Science",  url: "https://www.webofscience.com/" },
  { label: "PubMed",          url: "https://pubmed.ncbi.nlm.nih.gov/" },
  { label: "CrossRef",        url: "https://search.crossref.org/" },
];

export function WebViewPanel({ notify }: { notify: (s: string) => void }) {
  const [url, setUrl] = useState(PRESETS[0].url);
  const [draft, setDraft] = useState(url);

  function go() {
    let next = draft.trim();
    if (!next) return;
    if (!/^https?:\/\//.test(next)) next = "https://" + next;
    setUrl(next);
    setDraft(next);
    notify(`已跳转到 ${next}`);
  }

  return (
    <div className="web-pane">
      <div className="web-toolbar">
        <input
          className="url-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && go()}
          placeholder="输入网址，回车跳转"
        />
        <button className="primary-btn" onClick={go}>跳转</button>
        <div className="presets">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              className="preset-btn"
              onClick={() => { setDraft(p.url); setUrl(p.url); }}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
      <div className="web-frame-wrap">
        <iframe className="web-frame" src={url} title="webview" />
      </div>
    </div>
  );
}
