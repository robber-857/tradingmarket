import { useEffect, useRef, useState } from "react";
import ResearchWorkspace from "./ResearchWorkspace";
import MacroCalendar from "./MacroCalendar";
import NewsWorkspace from "./NewsWorkspace";
import DailyBrief from "./DailyBrief";
import HomeOverview from "./HomeOverview";
import BrandMark from "./BrandMark";
import OptionsWorkspace from "./OptionsWorkspace";
import OptionStrategies from "./OptionStrategies";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  Bookmark,
  CalendarDays,
  ChartNoAxesCombined,
  Check,
  ChevronRight,
  ChevronsUpDown,
  CircleHelp,
  Clock3,
  Download,
  ExternalLink,
  FileChartColumn,
  Globe2,
  LayoutDashboard,
  Menu,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Star,
  Sun,
  Moon,
  TrendingUp,
  Users,
  X,
  Zap,
} from "lucide-react";
import {
  assets,
  events,
  news,
  views,
  initialCourses,
  lessonText,
} from "./data";

const navGroups = [
  {
    label: "工作空间",
    items: [
      ["overview", "市场总览", LayoutDashboard],
      ["news", "市场热点", Zap],
      ["daily", "每日市场简报", FileChartColumn],
      ["calendar", "宏观与事件", CalendarDays],
      ["opinions", "多方观点", Users],
      ["sentiment", "市场情绪", Activity],
    ],
  },
  {
    label: "深度研究",
    items: [
      ["financials", "财报分析", FileChartColumn],
      ["fundamentals", "基本面分析", ChartNoAxesCombined],
      ["options", "期权分析", Activity],
      ["strategies", "期权策略", SlidersHorizontal],
      ["watchlist", "我的关注", Star],
    ],
  },
  { label: "学习与成长", items: [["academy", "交易学院", BookOpen]] },
];
const navItems = navGroups.flatMap((g) => g.items);
const titles = Object.fromEntries(navItems.map(([key, name]) => [key, name]));
const descriptions = {
  overview: "今日重点、关键日程与资产研究，从这里开始。",
  news: "筛选重要信息，理解事件背后的市场传导。",
  daily: "每日重点、市场影响与风险，保留生成时的原始证据。",
  options: "从真实期权链理解持仓分布、波动成本与财报预期。",
  strategies: "连接真实期权链，比较策略盈亏、组合敏感度与风险。",
  calendar: "提前了解关键数据，用事实校准市场预期。",
  opinions: "把不同判断放在一起，理解共识，也看见分歧。",
  sentiment: "观察讨论的变化，让情绪成为研究的一个维度。",
  financials: "从三张报表出发，理解公司的经营质量。",
  fundamentals: "理解资产价值的驱动因素与关键风险。",
  watchlist: "把你的研究对象，放在同一个视野里。",
  academy: "让每一次关注市场，都成为一次积累。",
  settings: "管理研究偏好与数据来源。",
};
function useStored(key, initial) {
  const [v, setV] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(key)) ?? initial;
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(v));
    } catch {
      // Private browsing or a full quota must not interrupt the workspace.
      console.warn("Local preferences could not be saved.");
    }
  }, [key, v]);
  return [v, setV];
}
function Badge({ children, tone = "" }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function PanelTitle({ icon: Icon, title, sub, action, onClick }) {
  return (
    <div className="panel-title">
      <div>
        <h2>
          {Icon && <Icon size={17} />} {title}
        </h2>
        {sub && <p>{sub}</p>}
      </div>
      {action && (
        <button className="text-button" onClick={onClick}>
          {action}
          <ArrowRight size={14} />
        </button>
      )}
    </div>
  );
}
function Sparkline({ values, color = "var(--success)" }) {
  const pts = values.map((v, i) => `${i * 7},${55 - v * 0.6}`).join(" ");
  return (
    <svg
      className="sparkline"
      viewBox="0 0 105 55"
      aria-label="演示价格走势"
      role="img"
    >
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
function Chart({ period = "1周", market = "全部市场", large = false }) {
  const [hover, setHover] = useState(null);
  const shift = ["1天", "1周", "1月", "3月"].indexOf(period);
  const equity = Array.from({ length: 39 }, (_, i) =>
    Math.max(
      0,
      Math.min(
        8,
        i * 0.16 +
          (Math.sin(i * 1.7 + shift) - Math.sin(shift)) * 0.55 +
          (Math.cos(i * 0.55 + shift) - Math.cos(shift)) * 0.7,
      ),
    ),
  );
  const b = equity.map((v, i) =>
    Math.max(
      0,
      Math.min(8, v * 0.78 + (Math.sin(i * 0.9 + 3) - Math.sin(3)) * 0.7),
    ),
  );
  const a = market === "加密货币" ? b : equity;
  const labels = {
    "1天": ["09:00", "11:00", "13:00", "15:00", "17:00", "19:00", "21:00"],
    "1周": ["11/02", "11/03", "11/04", "11/05", "11/06", "11/07", "11/08"],
    "1月": ["10/09", "10/14", "10/19", "10/24", "10/29", "11/03", "11/08"],
    "3月": ["08/08", "08/23", "09/08", "09/23", "10/08", "10/23", "11/08"],
  }[period];
  const point = (v, i) => `${48 + i * 17.3},${200 - v * 21.5}`;
  const path = (arr) =>
    arr.map((v, i) => (i ? "L" : "M") + point(v, i)).join(" ");
  return (
    <div
      className={`chart ${large ? "large" : ""}`}
      onMouseLeave={() => setHover(null)}
    >
      <svg
        viewBox="0 0 740 250"
        role="img"
        aria-label={`${market}${period}演示标准化走势`}
      >
        <defs>
          <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent-muted)" stopOpacity=".24" />
            <stop offset="100%" stopColor="var(--accent-muted)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3, 4].map((i) => (
          <g key={i}>
            <line
              x1="48"
              x2="712"
              y1={28 + i * 43}
              y2={28 + i * 43}
              stroke="var(--border)"
              strokeDasharray="3 4"
            />
            <text x="4" y={32 + i * 43} fill="var(--muted)" fontSize="10">
              {(4 - i) * 2}%
            </text>
          </g>
        ))}
        <path d={`${path(a)} L705,200 L48,200 Z`} fill="url(#area)" />
        <path
          className="draw-line"
          d={path(a)}
          fill="none"
          stroke="var(--text)"
          strokeWidth="2.4"
        />
        {market === "全部市场" && (
          <path
            className="draw-line secondary"
            d={path(b)}
            fill="none"
            stroke="var(--border-strong)"
            strokeWidth="2"
            strokeDasharray="5 4"
          />
        )}
        {labels.map((s, i) => (
          <text key={s} x={48 + i * 109.5} y="235" fill="var(--muted)" fontSize="10">
            {s}
          </text>
        ))}
        {a.map((v, i) => (
          <rect
            key={i}
            x={40 + i * 17.3}
            y="10"
            width="18"
            height="200"
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          />
        ))}
        {hover !== null && (
          <g pointerEvents="none">
            <line
              x1={48 + hover * 17.3}
              x2={48 + hover * 17.3}
              y1="15"
              y2="205"
              stroke="var(--border-strong)"
              strokeDasharray="3 3"
            />
            <circle
              cx={48 + hover * 17.3}
              cy={200 - a[hover] * 21.5}
              r="4"
              fill="var(--text)"
              stroke="white"
              strokeWidth="2"
            />
            <rect
              x={Math.min(590, 48 + hover * 17.3)}
              y="0"
              width="100"
              height="30"
              rx="6"
              fill="var(--text)"
            />
            <text
              x={Math.min(602, 60 + hover * 17.3)}
              y="20"
              fill="white"
              fontSize="11"
            >
              演示 +{a[hover].toFixed(2)}%
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}

export default function App() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme === "darkness" ? "darkness" : "lightness");
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "darkness" ? "#212121" : "#ffffff");
    try { localStorage.setItem("meridian-theme", theme); } catch { /* Theme still works without storage. */ }
  }, [theme]);
  const [page, setPage] = useState(() => location.hash.slice(1) || "overview");
  const [mobile, setMobile] = useState(false);
  const [optionSeed,setOptionSeed]=useState(null);
  const [strategySeed,setStrategySeed]=useState(null);
  const [homeNewsSeed,setHomeNewsSeed]=useState(null);
  const [homeEventSeed,setHomeEventSeed]=useState(null);
  const [homeBriefDay,setHomeBriefDay]=useState('');
  const [market, setMarket] = useState("全部市场");
  const [period, setPeriod] = useState("1周");
  const [modal, setModal] = useState(null);
  const [toast, setToast] = useState("");
  const [query, setQuery] = useState("");
  const [directoryAssets, setDirectoryAssets] = useState([]);
  const [directoryError, setDirectoryError] = useState("");
  const [directoryBusy, setDirectoryBusy] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  useEffect(() => {
    if (!searchOpen) return;
    const c = new AbortController();
    setDirectoryAssets([]);setDirectoryError("");setDirectoryBusy(true);
    const timer = setTimeout(async () => {
      try {
        const r = await fetch(`/api/research/assets?q=${encodeURIComponent(query.trim())}`, {signal:c.signal});
        const data = await r.json();
        if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "股票目录暂不可用");
        if (!c.signal.aborted) setDirectoryAssets(data.results.map((a) => ({...a,en:a.english,type:"美股",color:"var(--surface-selected)"})));
      } catch(e) {if (!c.signal.aborted) setDirectoryError("官方股票目录暂不可用，可在研究页面重试。");}
      finally {if (!c.signal.aborted) setDirectoryBusy(false);}
    },250);
    return () => {clearTimeout(timer);c.abort();};
  }, [query,searchOpen]);
  const searchableAssets = [...directoryAssets,...assets.filter((a) => !directoryAssets.some((d) => d.symbol === a.symbol))];
  const [asset, setAsset] = useState("INTC");
  const [assetQuery, setAssetQuery] = useState("");
  const [eventFilter, setEventFilter] = useState("即将发布");
  const [watch, setWatch] = useStored("meridian-watch", [
    "NVDA",
    "BTC",
    "AAPL",
  ]);
  const [reminders, setReminders] = useStored("meridian-reminders", []);
  const [savedNews, setSavedNews] = useStored("meridian-saved", []);
  const [courses, setCourses] = useStored("meridian-courses", initialCourses);
  const [completed, setCompleted] = useStored("meridian-completed", []);
  const [keywords, setKeywords] = useStored("meridian-keywords", [
    "Bitcoin",
    "Federal Reserve",
    "NVIDIA",
  ]);
  const [keyword, setKeyword] = useState("");
  const [sentimentFilter, setSentimentFilter] = useState("全部");
  const [courseFilter, setCourseFilter] = useState("全部课程");
  const [settings, setSettings] = useStored("meridian-settings", {
    timezone: "America/New_York",
    digest: true,
  });
  const [editor, setEditor] = useState({
    title: "",
    summary: "",
    category: "宏观入门",
    body: "",
  });
  const modalRef = useRef(null);
  const toastTimer = useRef(null);
  const navigate = (p) => {
    setPage(p);
    location.hash = p;
    setMobile(false);
    setSearchOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const notify = (text) => {
    setToast(text);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 3200);
  };
  useEffect(() => {
    const handler = () => setPage(location.hash.slice(1) || "overview");
    window.addEventListener("hashchange", handler);
    return () => window.removeEventListener("hashchange", handler);
  }, []);
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
      if (e.key === "Escape") {
        setModal(null);
        setSearchOpen(false);
        setMobile(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  useEffect(() => {
    if (!modal && !searchOpen) return;
    const before = document.activeElement;
    document.body.style.overflow = "hidden";
    const timer = setTimeout(
      () =>
        modalRef.current
          ?.querySelector("input,button,select,textarea")
          ?.focus(),
      50,
    );
    const trap = (e) => {
      if (e.key !== "Tab") return;
      const list = modalRef.current?.querySelectorAll(
        "button:not([disabled]),input,select,textarea,a[href]",
      );
      if (!list?.length) return;
      const first = list[0],
        last = list[list.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", trap);
    return () => {
      clearTimeout(timer);
      document.body.style.overflow = "";
      document.removeEventListener("keydown", trap);
      before?.focus();
    };
  }, [modal, searchOpen]);
  const toggleWatch = (s) => {
    setWatch((v) => (v.includes(s) ? v.filter((x) => x !== s) : [...v, s]));
    notify(watch.includes(s) ? `已取消关注 ${s}` : `已关注 ${s}`);
  };
  const toggleReminder = (id) => {
    setReminders((v) =>
      v.includes(id) ? v.filter((x) => x !== id) : [...v, id],
    );
    notify(
      reminders.includes(id)
        ? "已取消提醒标记"
        : "已加入提醒清单；暂不发送推送通知",
    );
  };
  const exportBrief = () => {
    const text = `霁明 Clarora｜市场研究演示简报\n2026-11-08｜全部为模拟数据，不是实时行情或投资建议\n\n市场观察：关注通胀数据、就业变化与企业盈利。\n\n我的关注：${watch.join("、")}\n\n关键事件（演示排期）：\n${events.map((e) => `${e.title}：预期 ${e.forecast}，前值 ${e.previous}，公布值 ${e.actual}`).join("\n")}\n\n观点占比为虚构样本分布，不代表上涨概率。`;
    const u = URL.createObjectURL(
      new Blob(["\uFEFF" + text], { type: "text/plain;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = u;
    link.download = "Clarora-研究演示简报.txt";
    link.click();
    URL.revokeObjectURL(u);
    notify("演示简报已导出");
  };
  const openAsset = (a, dest = "fundamentals") => {
    setAsset(a.symbol);
    setAssetQuery("");
    navigate(dest);
  };
  function EventRows({ compact = false }) {
    const list = compact
      ? events.slice(0, 3)
      : eventFilter === "已公布"
        ? events.filter((e) => e.actual !== "待公布")
        : eventFilter === "全部事件"
          ? events
          : events.filter((e) => e.actual === "待公布");
    return (
      <div className="event-list">
        {list.map((e) => (
          <div className="event-row" key={e.id}>
            <div className="event-date">
              <strong>{e.day}</strong>
              <span>11月 · {e.weekday}</span>
            </div>
            <button
              className="event-main"
              onClick={() => setModal({ type: "event", data: e })}
            >
              <span className="event-meta">
                {e.time} ET{" "}
                <span className={`impact ${e.impact === "高" ? "high" : ""}`}>
                  ● {e.impact}影响
                </span>
              </span>
              <strong>{compact ? e.short : e.title}</strong>
              <span className="muted">
                前值 {e.previous} <span className="divider">/</span> 预期{" "}
                <b>{e.forecast}</b>
                {e.actual !== "待公布" && ` / 公布 ${e.actual}`}
              </span>
            </button>
            <button
              className={`icon-button reminder ${reminders.includes(e.id) ? "selected" : ""}`}
              aria-label={`${reminders.includes(e.id) ? "取消" : "关注"}${e.short}提醒`}
              onClick={() => toggleReminder(e.id)}
            >
              {reminders.includes(e.id) ? (
                <Check size={17} />
              ) : (
                <Bell size={17} />
              )}
            </button>
          </div>
        ))}
      </div>
    );
  }
  function SentimentGauge() {
    return (
      <div className="gauge-wrap">
        <div className="gauge">
          <svg
            viewBox="0 0 260 145"
            role="img"
            aria-label="演示市场情绪指数 68，偏乐观"
          >
            <path
              d="M28 126 A102 102 0 0 1 232 126"
              fill="none"
              stroke="var(--border)"
              strokeWidth="18"
              strokeLinecap="round"
            />
            <path
              d="M28 126 A102 102 0 0 1 232 126"
              fill="none"
              stroke="var(--border-strong)"
              strokeWidth="18"
              strokeLinecap="round"
              pathLength="100"
              strokeDasharray="68 100"
            />
            <path
              d="M130 126 L185 66"
              stroke="var(--text)"
              strokeWidth="3"
              strokeLinecap="round"
            />
            <circle cx="130" cy="126" r="7" fill="var(--text)" />
            <text
              x="130"
              y="94"
              textAnchor="middle"
              fill="var(--text)"
              fontSize="38"
              fontWeight="600"
            >
              68
              <tspan fontSize="12" fill="var(--muted)">
                {" "}
                /100
              </tspan>
            </text>
          </svg>
          <div className="gauge-labels">
            <span>谨慎</span>
            <strong>偏乐观</strong>
            <span>乐观</span>
          </div>
        </div>
        <div className="sentiment-split">
          <span>
            <i className="dot green" />
            看多 <b>58%</b>
          </span>
          <span>
            <i className="dot neutral" />
            中性 <b>27%</b>
          </span>
          <span>
            <i className="dot bear" />
            看空 <b>15%</b>
          </span>
        </div>
        <div className="stacked">
          <i style={{ width: "58%" }} />
          <i style={{ width: "27%" }} />
          <i style={{ width: "15%" }} />
        </div>
        <p className="fine-print">虚构帖子样本 · 占比不代表涨跌概率</p>
      </div>
    );
  }
  function ViewRows() {
    return (
      <div className="views-list">
        {views.map((v) => (
          <div className="view-row" key={v.name}>
            <div className="view-who">
              <span className="avatar" style={{ background: v.color }}>
                {v.initial}
              </span>
              <div>
                <strong>{v.name}</strong>
                <span>{v.role}</span>
              </div>
            </div>
            <div className="view-opinion">
              <Badge tone="green">{v.stance}</Badge>
              <p>{v.text}</p>
            </div>
            <div className="view-bar">
              <div className="stacked">
                <i style={{ width: `${v.bull}%` }} />
                <i style={{ width: `${v.neutral}%` }} />
                <i style={{ width: `${v.bear}%` }} />
              </div>
              <span>
                看多 {v.bull}%{" "}
                <span>
                  中性 {v.neutral}% · 看空 {v.bear}%
                </span>
              </span>
            </div>
          </div>
        ))}
      </div>
    );
  }
  function renderOverview() {
    return <HomeOverview timezone={settings.timezone} watch={watch} onNavigate={navigate}
      onNews={(article,snapshot,category='all')=>{setHomeNewsSeed({article,snapshot,category});navigate('news');}}
      onEvent={event=>{setHomeEventSeed(event);navigate('calendar');}}
      onBrief={day=>{setHomeBriefDay(day);navigate('daily');}}
      onResearch={(symbol,dest)=>{setAsset(symbol);if(dest==='options')setOptionSeed({symbol});navigate(dest);}} />;
  }
  function renderFinancials() {
    return (
      <ResearchWorkspace
        mode="financials"
        symbol={asset}
        onSymbolChange={setAsset}
        isWatched={watch.includes(asset)}
        onToggleWatch={() => toggleWatch(asset)}
      />
    );
  }
  function renderFundamentals() {
    return (
      <ResearchWorkspace
        mode="fundamentals"
        symbol={asset}
        onSymbolChange={setAsset}
        isWatched={watch.includes(asset)}
        onToggleWatch={() => toggleWatch(asset)}
      />
    );
  }
  function renderNews() {
    return <NewsWorkspace timezone={settings.timezone} initialSelection={homeNewsSeed} />;
  }
  function renderCalendar() {
    return <MacroCalendar initialTimezone={settings.timezone} initialEvent={homeEventSeed} />;
  }
  function renderOpinions() {
    return (
      <>
        <div className="notice">
          <Users size={18} />
          <div>
            <b>观点分布，不是价格预测</b>
            <p>
              以下为虚构样本。百分比展示观点分类占比；真实版本需显示样本数量、采样时间和分类方法。
            </p>
          </div>
        </div>
        <section className="panel">
          <PanelTitle
            title="市场方向 · 多方观点对比"
            sub="观察主题：增长、通胀与货币政策 · 演示窗口：最近 7 天"
          />
          <ViewRows />
        </section>
        <div className="scenario-grid opinion-scenarios">
          {[
            ["共识所在", "通胀走势与盈利兑现，是下一阶段需要共同验证的变量。"],
            [
              "分歧所在",
              "市场对政策节奏和增长韧性的判断不同，同一数据可能产生不同解读。",
            ],
            [
              "如何验证",
              "持续记录观点的条件与失效点，回看原始数据，不按头衔替代证据。",
            ],
          ].map(([t, d], i) => (
            <article key={t}>
              <span>0{i + 1}</span>
              <h3>{t}</h3>
              <p>{d}</p>
            </article>
          ))}
        </div>
      </>
    );
  }
  function renderSentiment() {
    const posts = [
      {
        name: "Macro Observer",
        tag: "宏观",
        text: "The next inflation print matters, but the trend in services is what I’m watching. One data point isn’t a trend.",
        zh: "关注服务通胀趋势，单次数据不足以说明方向。",
        tone: "中性",
        score: "0.76",
      },
      {
        name: "Digital Asset Notes",
        tag: "加密",
        text: "Constructive on network adoption. I still want to see sustained spot demand before changing my view.",
        zh: "对网络采用偏积极，同时等待现货需求持续验证。",
        tone: "看多",
        score: "0.82",
      },
      {
        name: "Equity Research Lab",
        tag: "美股",
        text: "Higher capex is not automatically higher earnings. Watching cash conversion closely this quarter.",
        zh: "资本开支增加不一定等于盈利增加，关注现金转化。",
        tone: "谨慎",
        score: "0.71",
      },
    ];
    return (
      <>
        <div className="notice">
          <Activity size={18} />
          <div>
            <b>X 情绪研究 · 演示模式</b>
            <p>
              当前使用虚构帖子，尚未连接 X
              或运行采集器。分类分数为演示值，不代表模型已完成验证。
            </p>
          </div>
          <button
            className="button"
            onClick={() => setModal({ type: "method" })}
          >
            <SlidersHorizontal size={15} />
            方法说明
          </button>
        </div>
        <div className="sentiment-layout">
          <section className="panel">
            <PanelTitle
              title="讨论情绪分布"
              sub="模拟样本窗口 · 最近 24 小时"
            />
            <SentimentGauge />
          </section>
          <section className="panel">
            <PanelTitle
              title="监测主题"
              sub="设置保存在本机，后续可连接授权数据源。"
            />
            <div className="keyword-list">
              {keywords.map((k) => (
                <span key={k}>
                  {k}
                  <button
                    aria-label={`移除关键词 ${k}`}
                    onClick={() => setKeywords((v) => v.filter((x) => x !== k))}
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
            <form
              className="keyword-form"
              onSubmit={(e) => {
                e.preventDefault();
                const k = keyword.trim();
                if (!k) return;
                if (keywords.some((x) => x.toLowerCase() === k.toLowerCase())) {
                  notify("这个关键词已存在");
                  return;
                }
                setKeywords((v) => [...v, k]);
                setKeyword("");
                notify("关键词已保存在本机");
              }}
            >
              <input
                aria-label="新的监测关键词"
                value={keyword}
                maxLength={50}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="输入关键词，如 $BTC"
              />
              <button className="button primary" type="submit">
                <Plus size={15} />
                添加
              </button>
            </form>
            <div className="pipeline">
              <span>主题与账号</span>
              <ArrowRight size={14} />
              <span>去重与筛选</span>
              <ArrowRight size={14} />
              <span>情绪分类</span>
            </div>
            <p className="fine-print">
              规划流程：授权采集 → 语言与资产识别 → 去重 → 情绪分类 →
              人工抽样复核。
            </p>
          </section>
        </div>
        <section className="panel">
          <PanelTitle
            title="讨论样本"
            sub="以下账号和内容均为虚构，不指向真实 X 用户。"
          />
          <div className="tabs">
            {["全部", "宏观", "美股", "加密"].map((t) => (
              <button
                key={t}
                className={sentimentFilter === t ? "active" : ""}
                onClick={() => setSentimentFilter(t)}
              >
                {t}
              </button>
            ))}
          </div>
          {posts
            .filter(
              (p) => sentimentFilter === "全部" || p.tag === sentimentFilter,
            )
            .map((p) => (
              <article className="post" key={p.name}>
                <span className="avatar">{p.name[0]}</span>
                <div>
                  <div className="spread">
                    <strong>
                      {p.name} <span className="muted">· 虚构账号</span>
                    </strong>
                    <Badge tone={p.tone === "看多" ? "green" : ""}>
                      {p.tone}
                    </Badge>
                  </div>
                  <p>{p.text}</p>
                  <div className="translation">{p.zh}</div>
                  <span className="fine-print">
                    {p.tag} · 示例分类分数 {p.score} · 需人工复核
                  </span>
                </div>
              </article>
            ))}
        </section>
      </>
    );
  }
  function renderWatchlist() {
    return (
      <section className="panel">
        <PanelTitle
          title="我的研究清单"
          sub={`${watch.length} 个关注资产 · 保存在当前浏览器`}
          action="添加资产"
          onClick={() => setSearchOpen(true)}
        />
        {watch.length ? (
          <div className="table-wrap">
            <table className="watch-table">
              <thead>
                <tr>
                  <th>资产</th>
                  <th>模拟价格 / USD</th>
                  <th>模拟涨跌</th>
                  <th>走势</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {watch.map((s) => assets.find((a) => a.symbol === s) || {symbol:s,name:"已关注美股 · 点击研究",type:"美股",price:"—",change:"—",values:[],color:"var(--surface-selected)"})
                  .map((a) => (
                    <tr key={a.symbol}>
                      <td>
                        <button
                          className="asset-table-name"
                          onClick={() => openAsset(a)}
                        >
                          <span
                            className="asset-logo"
                            style={{ background: a.color }}
                          >
                            {a.symbol[0]}
                          </span>
                          <span>
                            <b>{a.symbol}</b>
                            <small>{a.name}</small>
                          </span>
                        </button>
                      </td>
                      <td>{a.price}</td>
                      <td className={a.change.includes("−") ? "down" : "up"}>
                        {a.change}
                      </td>
                      <td>
                        {a.values.length ? <Sparkline values={a.values} /> : <span className="muted">研究页查看行情</span>}
                      </td>
                      <td>
                        <button
                          className="icon-button"
                          aria-label={`移除关注 ${a.symbol}`}
                          onClick={() => toggleWatch(a.symbol)}
                        >
                          <Star size={17} fill="currentColor" />
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            <Star size={36} />
            <h3>从一个资产开始研究</h3>
            <p>搜索资产，然后加入关注清单。</p>
            <button
              className="button primary"
              onClick={() => setSearchOpen(true)}
            >
              添加资产
              <Plus size={16} />
            </button>
          </div>
        )}
      </section>
    );
  }
  function renderAcademy() {
    const list = courses.filter(
      (c) =>
        courseFilter === "全部课程" ||
        (courseFilter === "已完成" && completed.includes(c.id)) ||
        c.category === courseFilter,
    );
    return (
      <>
        <section className="academy-banner">
          <div>
            <span className="eyebrow">CLARORA ACADEMY</span>
            <h2>建立框架，让信息成为认知。</h2>
            <p>从宏观到基本面，用系统的方法理解市场。</p>
            <button
              className="button"
              onClick={() => setModal({ type: "lesson", data: courses[0] })}
            >
              从第一课开始
              <ArrowRight size={16} />
            </button>
          </div>
          <div className="academy-visual" aria-hidden="true">
            <BookOpen size={88} strokeWidth={0.8} />
            <span className="orbital o1" />
            <span className="orbital o2" />
          </div>
        </section>
        <div className="overview-toolbar">
          <div className="tabs">
            {["全部课程", "宏观入门", "基本面研究", "交易心理", "已完成"].map(
              (t) => (
                <button
                  key={t}
                  className={courseFilter === t ? "active" : ""}
                  onClick={() => setCourseFilter(t)}
                >
                  {t}
                </button>
              ),
            )}
          </div>
          <button
            className="button"
            onClick={() => setModal({ type: "publish" })}
          >
            <Plus size={16} />
            发布内容
          </button>
        </div>
        <div className="course-grid">
          {list.map((c) => (
            <button
              className="course"
              key={c.id}
              onClick={() => setModal({ type: "lesson", data: c })}
            >
              <div className={`course-art ${c.art}`}>
                <span>{c.category}</span>
                {c.art === "orbit" ? (
                  <Globe2 size={90} strokeWidth={0.7} />
                ) : c.art === "bars" ? (
                  <ChartNoAxesCombined size={90} strokeWidth={0.7} />
                ) : (
                  <Activity size={90} strokeWidth={0.7} />
                )}
                <span className="course-level">{c.level}</span>
              </div>
              <div className="course-copy">
                <span className="eyebrow">{c.category}</span>
                <h3>{c.title}</h3>
                <p>{c.summary}</p>
                <div>
                  <span>
                    <Clock3 size={13} />
                    {c.duration}
                  </span>
                  {completed.includes(c.id) ? (
                    <Badge tone="green">已完成</Badge>
                  ) : (
                    <ArrowUpRight size={17} />
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
        {!list.length && (
          <div className="empty-state">
            <BookOpen size={36} />
            <h3>这里还没有课程</h3>
            <p>阅读课程后标记完成，或发布你的第一篇知识内容。</p>
          </div>
        )}
        <p className="fine-print academy-note">
          当前提供文字示例课程；你创建的课程仅自己可见，尚未公开发布。
        </p>
      </>
    );
  }
  function renderSettings() {
    return (
      <div className="settings-grid">
        <section className="panel settings-panel">
          <PanelTitle title="阅读与通知偏好" />
          <label>
            时区
            <select
              value={settings.timezone}
              onChange={(e) => {
                setSettings({ ...settings, timezone: e.target.value });
                notify("时区偏好已保存，宏观日历将按此显示");
              }}
            >
              <option value="America/New_York">美东时间 ET</option>
              <option value="Australia/Sydney">悉尼时间</option>
              <option value="Asia/Shanghai">北京时间</option>
            </select>
          </label>
          <p className="fine-print">
            宏观日历使用所选时区，自动处理夏令时；仅确认日期的事件保留美东日期。
          </p>
          <div className="setting-row">
            <div>
              <strong>每日市场简报</strong>
              <p>保存订阅意向，暂未连接邮件服务</p>
            </div>
            <button
              role="switch"
              aria-checked={settings.digest}
              aria-label="每日简报订阅意向"
              className={`switch ${settings.digest ? "on" : ""}`}
              onClick={() =>
                setSettings({ ...settings, digest: !settings.digest })
              }
            >
              <span />
            </button>
          </div>
        </section>
        <section className="panel settings-panel">
          <PanelTitle
            title="数据连接"
            sub="财报、研究行情与官方宏观数据已集成；市场新闻已连接公开来源；情绪看板仍为演示。"
          />
          {[
            "Twelve Data 研究行情",
            "市场新闻",
            "BLS / BEA / 美联储宏观数据",
            "SEC 公司财报",
            "X 授权数据接口",
            "链上数据供应商",
          ].map((t) => (
            <div className="connection-row" key={t}>
              <span>{t}</span>
              <Badge tone={t === "SEC 公司财报" || t === "Twelve Data 研究行情" || t === "BLS / BEA / 美联储宏观数据" || t === "市场新闻" ? "green" : ""}>
                {t === "SEC 公司财报" ? "已集成 · 动态代码目录" : t === "Twelve Data 研究行情" ? "已集成 · 按代码获取" : t === "BLS / BEA / 美联储宏观数据" ? "已集成 · 免费官方来源" : t === "市场新闻" ? "已集成 · 公开 RSS" : "待接入"}
              </Badge>
            </div>
          ))}
        </section>
      </div>
    );
  }
  const renderers = {
    overview: renderOverview,
    financials: renderFinancials,
    fundamentals: renderFundamentals,
    news: renderNews,
    daily: () => <DailyBrief initialDay={homeBriefDay} />,
    options: () => <OptionsWorkspace seed={optionSeed} onStrategies={seed => {setStrategySeed(seed);navigate('strategies');}} />,
    strategies: () => <OptionStrategies seed={strategySeed} onOptions={seed => {setOptionSeed(seed);navigate('options');}} />,
    calendar: renderCalendar,
    opinions: renderOpinions,
    sentiment: renderSentiment,
    watchlist: renderWatchlist,
    academy: renderAcademy,
    settings: renderSettings,
  };
  return (
    <div className="app-shell">
      {mobile && (
        <div className="sidebar-scrim" onClick={() => setMobile(false)} />
      )}
      <aside className={`sidebar ${mobile ? "open" : ""}`}>
        <button
          className="brand"
          onClick={() => navigate("overview")}
          aria-label="霁明 Clarora首页"
        >
          <BrandMark />
          <span className="brand-wordmark">
            霁明<span>CLARORA · 市场研究</span>
          </span>
        </button>
        <button
          className="workspace-picker"
          onClick={() => setModal({ type: "workspace" })}
        >
          <span className="workspace-icon"><BrandMark /></span>
          <span>
            个人研究空间<small>Personal workspace</small>
          </span>
          <ChevronsUpDown size={14} />
        </button>
        <nav>
          {navGroups.map((g) => (
            <div className="nav-group" key={g.label}>
              <span className="nav-label">{g.label}</span>
              {g.items.map(([key, label, Icon]) => (
                <button
                  key={key}
                  onClick={() => navigate(key)}
                  className={`nav-item ${page === key ? "active" : ""}`}
                  aria-current={page === key ? "page" : undefined}
                >
                  <Icon size={18} />
                  <span>{label}</span>
                  {key === "sentiment" && <span className="nav-new">BETA</span>}
                  {key === "watchlist" && (
                    <span className="nav-count subtle">{watch.length}</span>
                  )}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="plan-card">
            <div>
              <Sparkles size={17} />
              <span>更完整的市场视野</span>
            </div>
            <p>探索 Clarora Pro 研究空间</p>
            <button onClick={() => setModal({ type: "plan" })}>
              了解订阅计划
              <ArrowUpRight size={15} />
            </button>
          </div>
          <button
            className={`nav-item ${page === "settings" ? "active" : ""}`}
            onClick={() => navigate("settings")}
          >
            <Settings2 size={18} />
            <span>偏好与数据源</span>
          </button>
          <button
            className="profile"
            onClick={() => setModal({ type: "workspace" })}
          >
            <span className="avatar profile-avatar">L</span>
            <span>
              研究员<small>体验账户</small>
            </span>
            <ChevronsUpDown size={15} />
          </button>
        </div>
        <button
          className="sidebar-close icon-button"
          aria-label="关闭导航"
          onClick={() => setMobile(false)}
        >
          <X size={20} />
        </button>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="打开导航"
              onClick={() => setMobile(true)}
            >
              <Menu size={20} />
            </button>
            <span>工作空间</span>
            <ChevronRight size={13} />
            <strong>{titles[page] || "偏好与数据源"}</strong>
          </div>
          <div className="topbar-actions">
            <label className="theme-picker">
              {theme === "darkness" ? <Moon size={15} /> : <Sun size={15} />}
              <select aria-label="界面主题" value={theme} onChange={(event) => setTheme(event.target.value)}>
                <option value="lightness">Lightness</option>
                <option value="darkness">Darkness</option>
              </select>
            </label>
            <button
              className="global-search"
              onClick={() => setSearchOpen(true)}
            >
              <Search size={16} />
              <span>搜索资产、事件、课程...</span>
              <kbd>⌘ K</kbd>
            </button>
            <span className="topbar-separator" />
            <button
              className="icon-button notification-button"
              aria-label="查看提醒清单"
              onClick={() => setModal({ type: "notifications" })}
            >
              <Bell size={19} />
              {reminders.length > 0 && <i />}
            </button>
            <button
              className="top-avatar"
              aria-label="查看研究空间"
              onClick={() => setModal({ type: "workspace" })}
            >
              L
            </button>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="page-eyebrow">{page === "overview" ? "化繁为简，见微知明" : "CLARORA · MARKET RESEARCH"}</div>
              <h1>
                {titles[page] || "偏好与数据源"}
                {page === "overview" && <span className="heading-dot" />}
              </h1>
              <p>{descriptions[page] || descriptions.overview}</p>
            </div>
            <div className="heading-actions">
              <Badge
                tone={
                  ["overview", "financials", "fundamentals", "calendar", "news", "daily", "options", "strategies"].includes(page)
                    ? "green"
                    : "demo"
                }
              >
                <span className="status-dot" />
                {["overview", "financials", "fundamentals", "calendar", "news", "daily", "options", "strategies"].includes(page)
                  ? ({overview:"每日关注",calendar:"宏观数据",news:"真实新闻",daily:"AI 每日简报",options:"延迟期权链",strategies:"策略研究"}[page] || "财报研究")
                  : "演示模式"}
              </Badge>
              {!["overview", "financials", "fundamentals", "calendar", "news", "daily", "options", "strategies"].includes(page) && (
                <button className="button" onClick={exportBrief}>
                  <Download size={15} />
                  <span>导出简报</span>
                </button>
              )}
            </div>
          </div>
          <div className="page-content" key={page}>
            {(renderers[page] || renderOverview)()}
          </div>
          <footer>
            <span>
              <BrandMark className="footer-mark" /> 霁明 Clarora
            </span>
            <p><span className="brand-motto">化繁为简，见微知明</span><br />研究内容显示来源、时间与口径 · 多方观点、独立情绪页仍为演示</p>
            <button onClick={() => setModal({ type: "method" })}>
              数据与方法
              <ArrowUpRight size={12} />
            </button>
          </footer>
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <Check size={17} />
          {toast}
        </div>
      )}
      {(modal || searchOpen) && (
        <div
          className="modal-overlay"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) {
              setModal(null);
              setSearchOpen(false);
            }
          }}
        >
          <section
            ref={modalRef}
            className={`modal ${searchOpen ? "search-modal" : ""} ${["event", "news", "lesson", "brief"].includes(modal?.type) ? "reading-modal" : ""}`}
            role="dialog"
            aria-modal="true"
            aria-label={searchOpen ? "全局搜索" : "详情面板"}
          >
            <button
              className="modal-close icon-button"
              aria-label="关闭详情"
              onClick={() => {
                setModal(null);
                setSearchOpen(false);
              }}
            >
              <X size={20} />
            </button>
            {searchOpen ? (
              <>
                <div className="search-dialog-input">
                  <Search size={21} />
                  <input
                    autoFocus
                    aria-label="搜索资产、事件或课程"
                    placeholder="搜索资产、事件或课程..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                  <kbd>ESC</kbd>
                </div>
                <div className="search-results">
                  <p>资产研究</p>
                  {directoryBusy && <p role="status">正在搜索 SEC 官方目录…</p>}
                  {directoryError && <p role="alert">{directoryError}</p>}
                  {searchableAssets
                    .filter((a) =>
                      (a.symbol + a.name + a.en)
                        .toLowerCase()
                        .includes(query.toLowerCase()),
                    )
                    .map((a) => (
                      <button key={a.symbol} onClick={() => openAsset(a)}>
                        <span
                          className="asset-logo"
                          style={{ background: a.color }}
                        >
                          {a.symbol[0]}
                        </span>
                        <span>
                          <b>{a.symbol}</b> {a.name}
                        </span>
                        <small>{a.type}</small>
                        <ArrowUpRight size={16} />
                      </button>
                    ))}
                  <p>事件与页面</p>
                  {events
                    .filter((e) =>
                      e.title.toLowerCase().includes(query.toLowerCase()),
                    )
                    .map((e) => (
                      <button
                        key={e.id}
                        onClick={() => {
                          setSearchOpen(false);
                          setModal({ type: "event", data: e });
                        }}
                      >
                        <CalendarDays size={17} />
                        <span>{e.title}</span>
                        <ChevronRight size={15} />
                      </button>
                    ))}
                  {navItems
                    .filter(([, name]) => name.includes(query))
                    .map(([id, name, Icon]) => (
                      <button key={id} onClick={() => navigate(id)}>
                        <Icon size={17} />
                        <span>{name}</span>
                        <ChevronRight size={15} />
                      </button>
                    ))}
                  <p>课程</p>
                  {courses
                    .filter(
                      (c) =>
                        c.title.includes(query) || c.category.includes(query),
                    )
                    .map((c) => (
                      <button
                        key={c.id}
                        onClick={() => {
                          setSearchOpen(false);
                          setModal({ type: "lesson", data: c });
                        }}
                      >
                        <BookOpen size={17} />
                        <span>{c.title}</span>
                        <ChevronRight size={15} />
                      </button>
                    ))}
                  {query &&
                    !searchableAssets.some((a) =>
                      (a.symbol + a.name + a.en)
                        .toLowerCase()
                        .includes(query.toLowerCase()),
                    ) &&
                    !events.some((e) =>
                      e.title.toLowerCase().includes(query.toLowerCase()),
                    ) &&
                    !navItems.some(([, n]) => n.includes(query)) &&
                    !courses.some(
                      (c) =>
                        c.title.includes(query) || c.category.includes(query),
                    ) && (
                      <div className="empty-state">
                        <Search size={30} />
                        <h3>没有找到相关结果</h3>
                        <p>试试 NVDA、比特币、CPI 或宏观入门。</p>
                      </div>
                    )}
                </div>
              </>
            ) : (
              renderModal()
            )}
          </section>
        </div>
      )}
    </div>
  );
  function renderModal() {
    const d = modal?.data;
    switch (modal?.type) {
      case "event":
        return (
          <>
            <Badge tone="demo">模拟事件 · 非官方排期</Badge>
            <h2>{d.title}</h2>
            <p className="modal-meta">
              11月{d.day}日 · {d.time} ET · {d.source}
            </p>
            <div className="event-values">
              {[
                ["前值", d.previous],
                ["市场预期", d.forecast],
                ["公布值", d.actual],
              ].map(([t, v]) => (
                <div key={t}>
                  <span>{t}</span>
                  <strong>{v}</strong>
                </div>
              ))}
            </div>
            <h3>为什么值得关注</h3>
            <p>{d.description}</p>
            <div className="transmission">
              {d.channels.map((c, i) => (
                <span key={c}>
                  {i > 0 && <ArrowRight size={14} />}
                  <Badge>{c}</Badge>
                </span>
              ))}
            </div>
            <h3>不同结果，如何理解</h3>
            {d.scenarios.map((s) => (
              <p className="scenario" key={s}>
                {s}
              </p>
            ))}
            <p className="fine-print">
              以上为条件分析，并非确定的价格路径。演示数字不可作为交易依据。
            </p>
            <div className="modal-actions">
              <a
                className="button"
                href={d.url}
                target="_blank"
                rel="noreferrer"
              >
                查看官方数据来源
                <ExternalLink size={15} />
              </a>
              <button
                className="button primary"
                onClick={() => toggleReminder(d.id)}
              >
                {reminders.includes(d.id) ? (
                  <Check size={15} />
                ) : (
                  <Bell size={15} />
                )}{" "}
                {reminders.includes(d.id) ? "已加入提醒清单" : "加入提醒清单"}
              </button>
            </div>
          </>
        );
      case "news":
        return (
          <>
            <Badge tone="green">{d.tag} · 演示样稿</Badge>
            <h2>{d.title}</h2>
            <p className="modal-meta">
              {d.source} · 阅读 {d.read}
            </p>
            <p className="lead">{d.summary}</p>
            <div className="prose">
              {d.body.split("\n\n").map((p) => (
                <p key={p}>{p}</p>
              ))}
            </div>
            <div className="modal-actions">
              <Badge>{d.impact}</Badge>
              <button
                className="button"
                onClick={() => {
                  setSavedNews((v) =>
                    v.includes(d.id)
                      ? v.filter((x) => x !== d.id)
                      : [...v, d.id],
                  );
                  notify(
                    savedNews.includes(d.id) ? "已取消收藏" : "文章已收藏",
                  );
                }}
              >
                <Bookmark size={15} />
                {savedNews.includes(d.id) ? "已收藏" : "收藏文章"}
              </button>
            </div>
          </>
        );
      case "brief":
        return (
          <>
            <Badge tone="green">
              <Sparkles size={13} />
              市场研究简报 · 样稿
            </Badge>
            <h2>本周，先把注意力放在三个问题上。</h2>
            <p className="modal-meta">
              2026年11月08日 · 演示场景，不是实时市场结论
            </p>
            {[
              [
                "01 / 通胀",
                "数据是否改变了市场对利率路径的预期？先看核心分项和修正，再看收益率的反应。",
              ],
              [
                "02 / 盈利",
                "收入增长是否转化为现金流？重点比较财报、指引和当前估值包含的假设。",
              ],
              [
                "03 / 情绪",
                "乐观讨论是否有数据支撑？区分社交热度、真实资金流和价格已经反映的预期。",
              ],
            ].map(([t, p]) => (
              <div className="brief-section" key={t}>
                <h3>{t}</h3>
                <p>{p}</p>
              </div>
            ))}
            <div className="modal-actions">
              <span className="fine-print">
                先建立观察框架，再形成自己的判断。
              </span>
              <button className="button primary" onClick={exportBrief}>
                <Download size={15} />
                导出简报
              </button>
            </div>
          </>
        );
      case "notifications":
        return (
          <>
            <Badge>提醒清单</Badge>
            <h2>我的事件提醒</h2>
            <p>提醒标记保存在当前浏览器。尚未接入后台调度、邮件或系统推送。</p>
            {reminders.length ? (
              events
                .filter((e) => reminders.includes(e.id))
                .map((e) => (
                  <div className="notification-row" key={e.id}>
                    <CalendarDays size={19} />
                    <button
                      onClick={() => setModal({ type: "event", data: e })}
                    >
                      <strong>{e.short}</strong>
                      <small>
                        11月{e.day}日 · {e.time} ET · 模拟排期
                      </small>
                    </button>
                    <button
                      className="icon-button"
                      aria-label={`移除${e.short}提醒`}
                      onClick={() => toggleReminder(e.id)}
                    >
                      <X size={16} />
                    </button>
                  </div>
                ))
            ) : (
              <div className="empty-state">
                <Bell size={32} />
                <h3>还没有关注的事件</h3>
                <p>在经济日历中点击铃铛，即可加入清单。</p>
                <button
                  className="button primary"
                  onClick={() => {
                    setModal(null);
                    navigate("calendar");
                  }}
                >
                  查看经济日历
                  <ArrowRight size={15} />
                </button>
              </div>
            )}
          </>
        );
      case "lesson":
        return (
          <>
            <Badge tone="green">{d.category} · 文字样课</Badge>
            <h2>{d.title}</h2>
            <p className="modal-meta">{d.duration} · 当前提供概览课文</p>
            <p className="lead">{d.summary}</p>
            <div className="lesson-outline">
              <h3>课程大纲</h3>
              {d.lessons.map((l, i) => (
                <p key={l}>
                  <span>{String(i + 1).padStart(2, "0")}</span>
                  {l}
                </p>
              ))}
            </div>
            <div className="prose">
              {(d.body || lessonText[d.id] || d.summary)
                .split("\n\n")
                .map((p, i) => (
                  <p key={i}>{p}</p>
                ))}
            </div>
            <button
              className="button primary"
              onClick={() => {
                setCompleted((v) =>
                  v.includes(d.id) ? v.filter((x) => x !== d.id) : [...v, d.id],
                );
                notify(
                  completed.includes(d.id)
                    ? "已恢复为未完成"
                    : "学习进度已保存",
                );
              }}
            >
              <Check size={16} />
              {completed.includes(d.id)
                ? "已完成 · 点击撤销"
                : "标记本课已完成"}
            </button>
          </>
        );
      case "publish":
        return (
          <>
            <Badge>创作者工作台 · 体验版</Badge>
            <h2>发布知识内容</h2>
            <p>
              内容只保存在此浏览器，刷新后可继续查看。正式发布需要后台账户与权限。
            </p>
            <form
              className="publish-form"
              onSubmit={(e) => {
                e.preventDefault();
                if (
                  !editor.title.trim() ||
                  !editor.summary.trim() ||
                  !editor.body.trim()
                )
                  return;
                setCourses((v) => [
                  ...v,
                  {
                    ...editor,
                    title: editor.title.trim(),
                    summary: editor.summary.trim(),
                    body: editor.body.trim(),
                    id: `local-${Date.now()}`,
                    duration: "1 篇文章 · 文字课程",
                    level: "新内容",
                    art: "wave",
                    lessons: ["正文与研究笔记"],
                  },
                ]);
                setEditor({
                  title: "",
                  summary: "",
                  category: "宏观入门",
                  body: "",
                });
                setCourseFilter("全部课程");
                setModal(null);
                notify("课程已保存，仅自己可见");
              }}
            >
              <label>
                内容标题
                <input
                  required
                  maxLength={70}
                  value={editor.title}
                  onChange={(e) =>
                    setEditor({ ...editor, title: e.target.value })
                  }
                  placeholder="例如：如何读懂一份非农报告"
                />
              </label>
              <label>
                分类
                <select
                  value={editor.category}
                  onChange={(e) =>
                    setEditor({ ...editor, category: e.target.value })
                  }
                >
                  {["宏观入门", "基本面研究", "交易心理"].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </label>
              <label>
                一句话简介
                <input
                  required
                  maxLength={140}
                  value={editor.summary}
                  onChange={(e) =>
                    setEditor({ ...editor, summary: e.target.value })
                  }
                />
              </label>
              <label>
                正文
                <textarea
                  required
                  rows={6}
                  value={editor.body}
                  onChange={(e) =>
                    setEditor({ ...editor, body: e.target.value })
                  }
                  placeholder="写下你的知识内容、研究方法与练习..."
                />
              </label>
              <button className="button primary" type="submit">
                保存课程
                <ArrowRight size={15} />
              </button>
            </form>
          </>
        );
      case "method":
        return (
          <>
            <Badge>产品说明</Badge>
            <h2>数据与研究方法</h2>
            <div className="prose">
              <h3>霁明 Clarora</h3>
              <p className="brand-story-motto">云销雨霁，万象澄明。</p>
              <p>化繁为简，见微知明。拨云见理，观市有据。</p>
              <p>品牌名取意于王勃《滕王阁序》“云销雨霁，彩彻区明”，从“雨霁”与“区明”中各取一字。“云销雨霁，万象澄明”为品牌延展文案。</p>
              <h3>观其变，究其理，明其势。</h3>
              <p>以 AI 梳理市场信息，串联事件、数据与研究线索，让复杂研究更易理解，帮助你形成自己的判断。</p>
              <h3>研究有据</h3>
              <p>财报研究依据 SEC 官方披露，财务指标与估值提供计算口径、来源和假设。新闻与宏观事件保留来源和时间，缺失数据明确标注。AI 辅助解释已有信息，区分事实、推论与条件假设，不代替独立判断。</p>
              <h3>如何理解观点与情绪</h3>
              <p>观点与情绪页面目前展示示例内容。观点占比描述样本中的分类分布，不代表未来上涨概率，也不构成买卖建议。</p>
              <h3>你的研究记录</h3>
              <p>关注、收藏与学习进度会保留在当前浏览器，暂不支持跨设备同步。清除浏览器数据可能导致这些记录丢失。</p>
            </div>
          </>
        );
      case "plan":
        return (
          <>
            <Badge tone="green">CLARORA PRO · 规划中</Badge>
            <h2>为持续研究，留一个专属空间。</h2>
            <p>
              订阅制产品将由团队为客户开通账户，提供统一的市场研究与学习体验。
            </p>
            <div className="plan-features">
              {[
                "宏观事件与多方观点研究",
                "自选资产与个性化简报",
                "市场情绪与主题追踪",
                "交易知识与会员课程",
              ].map((t) => (
                <p key={t}>
                  <Check size={17} />
                  {t}
                </p>
              ))}
            </div>
            <div className="notice">
              <CircleHelp size={19} />
              <p>
                订阅服务尚未开放，浏览与体验不会产生扣费。
              </p>
            </div>
            <button
              className="button primary"
              onClick={() => {
                setModal(null);
                navigate("academy");
              }}
            >
              体验交易学院
              <ArrowRight size={15} />
            </button>
          </>
        );
      default:
        return (
          <>
            <Badge tone="green">PERSONAL WORKSPACE</Badge>
            <h2>你的个人研究空间</h2>
            <p>在霁明 Clarora 整理关注、回顾事件，持续积累研究。</p>
            <div className="workspace-stats">
              <div>
                <strong>{watch.length}</strong>
                <span>关注资产</span>
              </div>
              <div>
                <strong>{reminders.length}</strong>
                <span>关注事件</span>
              </div>
              <div>
                <strong>{completed.length}</strong>
                <span>完成课程</span>
              </div>
            </div>
            <p>
              当前为免登录体验。研究记录仅保留在当前浏览器，暂不支持跨设备同步。
            </p>
            <button
              className="button"
              onClick={() => {
                setModal(null);
                navigate("settings");
              }}
            >
              <Settings2 size={16} />
              管理偏好与数据源
            </button>
          </>
        );
    }
  }
}
