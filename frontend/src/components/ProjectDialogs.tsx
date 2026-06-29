/**
 * 项目相关对话框：
 * - CreateProjectDialog（创建，名字可空 → 后端用占位名）
 * - RenameDialog（选题阶段第 8 步用，把占位名改成正式名）
 */
import { useState } from "react";

export function CreateProjectDialog(props: {
  open: boolean;
  onClose: () => void;
  onCreate: (input: { name?: string; topic: string; perspective: string }) => void;
}) {
  const { open, onClose, onCreate } = props;
  const [name, setName] = useState("");
  const [topic, setTopic] = useState("");
  const [perspective, setPerspective] = useState("science");

  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h3>新建项目</h3>
          <button className="ghost-btn" onClick={onClose}>×</button>
        </header>

        <p className="muted-small">
          按 SPEC §7.1：可以先不填名字，进入选题阶段；最后第 8 步 AI 推荐选题后再确定项目名。
        </p>

        <label>
          项目名称 <span className="muted-small">（留空 = 自动生成占位名 未命名-时间戳）</span>
          <input
            className="text-input wide"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="可留空"
          />
        </label>

        <label>
          初始课程/学科信息（可选）
          <textarea
            className="text-input wide"
            rows={3}
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="如：钙钛矿光伏稳定性 / 材料化学课程作业..."
          />
        </label>

        <label>
          论文取向
          <select
            className="text-input"
            value={perspective}
            onChange={(e) => setPerspective(e.target.value)}
          >
            <option value="science">理科（实验/表征/机理）</option>
            <option value="social">社科（理论/研究设计/数据）</option>
            <option value="custom">自定义</option>
          </select>
        </label>

        <footer className="modal-foot">
          <button className="ghost-btn" onClick={onClose}>取消</button>
          <button
            className="primary-btn"
            onClick={() => {
              onCreate({
                name: name.trim() || undefined,
                topic: topic.trim(),
                perspective,
              });
              setName(""); setTopic("");
            }}
          >
            创建
          </button>
        </footer>
      </div>
    </div>
  );
}

export function RenameDialog(props: {
  open: boolean;
  oldName: string;
  onClose: () => void;
  onRename: (newName: string) => void;
}) {
  const { open, oldName, onClose, onRename } = props;
  const [newName, setNewName] = useState("");

  if (!open) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h3>重命名项目</h3>
          <button className="ghost-btn" onClick={onClose}>×</button>
        </header>

        <p>
          当前名称：<code>{oldName}</code>
        </p>
        <label>
          新名称
          <input
            className="text-input wide"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="如：钙钛矿叠层电池稳定性研究"
            autoFocus
          />
        </label>
        <p className="muted-small">
          目录会通过 <code>shutil.move</code> 物理改名。draft.md 内的标题暂保留旧名，可手动修改。
        </p>

        <footer className="modal-foot">
          <button className="ghost-btn" onClick={onClose}>取消</button>
          <button
            className="primary-btn"
            disabled={!newName.trim()}
            onClick={() => {
              const v = newName.trim();
              if (!v) return;
              onRename(v);
              setNewName("");
            }}
          >
            确认重命名
          </button>
        </footer>
      </div>
    </div>
  );
}
