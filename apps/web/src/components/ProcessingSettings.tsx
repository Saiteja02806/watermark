import { AudioLines, Cpu, ScanLine, Sparkles } from "lucide-react";
import type { Health, RenderSettings } from "../types";

interface ProcessingSettingsProps {
  health: Health | null;
  settings: RenderSettings;
  onChange: (settings: Partial<RenderSettings>) => void;
}

export function ProcessingSettings({
  health,
  settings,
  onChange,
}: ProcessingSettingsProps) {
  return (
    <aside className="settings-panel">
      <div className="settings-panel__heading">
        <span className="section-kicker">Output setup</span>
        <h2>Process video</h2>
        <p>Reconstruction runs locally. Review the mask edge before starting.</p>
      </div>

      <fieldset className="segmented-field">
        <legend>Quality</legend>
        <div>
          {(["fast", "balanced", "high"] as const).map((quality) => (
            <button
              type="button"
              key={quality}
              className={settings.quality === quality ? "is-selected" : ""}
              onClick={() => onChange({ quality })}
            >
              {quality}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className="segmented-field">
        <legend>Resolution</legend>
        <div>
          {(["480p", "720p"] as const).map((resolution) => (
            <button
              type="button"
              key={resolution}
              className={settings.resolution === resolution ? "is-selected" : ""}
              onClick={() => onChange({ resolution })}
            >
              {resolution}
            </button>
          ))}
        </div>
      </fieldset>

      <label className="select-field">
        <span>
          <ScanLine size={15} />
          Mask expansion
        </span>
        <select
          value={settings.maskExpansion}
          onChange={(event) =>
            onChange({
              maskExpansion: Number(event.currentTarget.value) as 2 | 4 | 8 | 12,
            })
          }
        >
          <option value={2}>2 px · precise</option>
          <option value={4}>4 px · recommended</option>
          <option value={8}>8 px · broad edge</option>
          <option value={12}>12 px · maximum</option>
        </select>
      </label>

      <label className="select-field">
        <span>
          <Cpu size={15} />
          Repair engine
        </span>
        <select
          value={settings.engine}
          onChange={(event) =>
            onChange({
              engine: event.currentTarget.value as RenderSettings["engine"],
            })
          }
        >
          <option value="auto">
            Auto · {health?.propainter ? "ProPainter available" : "CPU fallback"}
          </option>
          <option value="opencv">OpenCV · fast local proof</option>
          <option value="propainter" disabled={!health?.propainter}>
            ProPainter {!health?.propainter ? "· not installed" : ""}
          </option>
        </select>
      </label>

      <label className="toggle-field">
        <span className="toggle-field__copy">
          <AudioLines size={16} />
          <span>
            <strong>Preserve original audio</strong>
            <small>Reattached without sending media away</small>
          </span>
        </span>
        <input
          type="checkbox"
          checked={settings.preserveAudio}
          onChange={(event) =>
            onChange({ preserveAudio: event.currentTarget.checked })
          }
        />
      </label>

      {!health?.propainter && (
        <div className="engine-note">
          <Sparkles size={16} />
          <p>
            The CPU engine is functional but less temporally consistent.
            Install ProPainter before quality-critical exports.
          </p>
        </div>
      )}
    </aside>
  );
}

