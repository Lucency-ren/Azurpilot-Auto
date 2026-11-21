// 配置分组渲染（从 ConfigPage 抽出的可复用部分）。
//
// 为什么抽出来：「工具」类任务（page=tool，如半自动点击/性能测试）在老 UI 里
// 走的是 alas_daemon_overview —— **和普通配置页用的是同一套 DOM 契约**，
// 只是页面顶部多一条调度器栏。所以配置卡的渲染必须共用一份，否则两边样式会漂。
//
// DOM 契约与 ConfigPage 完全一致（见 config/index.tsx 顶部说明）：
//   #pywebio-scope-group_{组名} > <p>标题</p> + <hr.hr-group> +
//   #pywebio-scope-arg_container-{类型}-{参数名}
import { useEffect, useRef, useState } from 'react'
import { instSeg } from '../../api/client'
import { PriorityFilter, isPriorityList } from './PriorityFilter'

export type ArgOption = { label: string; value: string }
export type Arg = {
  name: string; title: string; help: string;
  type: string; value: any; option: ArgOption[]
}
export type Group = { group: string; title: string; args: Arg[] }

/**
 * 多选控件：折叠成一个小框，点开才展开全部选项。
 *
 * 老 UI（module/webui/widgets.py:1054 put_arg_multiselect）是竖排复选框全铺开，
 * 「附加索引」有 13 个选项，一行就被撑成半屏高（长卿 2026-11-21：
 * 「你别给全部直接摆出来呀…折叠到那个小框里面点一下全部再展开」）。
 *
 * 值语义：按 option 原顺序回传字符串数组，后端 parse_pin_value
 * （module/webui/utils.py:867-873）用 `str(option)` 反查原始类型，
 * 委托商店那种数字 option（3 → "3" → 3）不会退化成字符串。
 */
function MultiSelect({ arg, onChange }: { arg: Arg; onChange: (v: any) => void }) {
  const options = arg.option || []
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)
  const current = new Set(
    (Array.isArray(arg.value) ? arg.value : arg.value === null || arg.value === undefined ? [] : [arg.value])
      .map(String),
  )
  // 点空白处 / Esc 收起（弹层不常驻，避免挡住下面的参数）
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const selectedLabels = options.filter(o => current.has(String(o.value))).map(o => o.label)
  const summary = selectedLabels.length ? selectedLabels.join('、') : '未选择'
  return (
    <div ref={boxRef} style={{ position: 'relative', display: 'flex', alignItems: 'stretch', gap: 4 }}>
      {/* 外形与普通 select 一致（长卿 2026-11-21：像「阵营」那种下拉一样适应宽度） */}
      <div
        role="button"
        tabIndex={0}
        aria-haspopup="true"
        aria-expanded={open}
        className="form-control config-multiselect-trigger"
        title={summary}
        onClick={() => setOpen(v => !v)}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setOpen(v => !v)
          }
        }}
        style={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          alignItems: 'center',
          cursor: 'pointer',
          userSelect: 'none',
        }}
      >
        <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {summary}
        </span>
        <span aria-hidden="true" style={{ flex: '0 0 auto', opacity: 0.65 }}>▾</span>
      </div>
      {/* 多选专用按钮：展开 ☑ 列表（单选仍是普通 select，不出现这个按钮） */}
      <button
        type="button"
        className="config-multiselect-btn"
        title={open ? '收起选项' : '多选'}
        aria-label={open ? '收起选项' : '多选'}
        aria-expanded={open}
        onClick={() => setOpen(v => !v)}
      >
        ☑
      </button>
      {open && (
        <div className="config-multiselect-panel">
          {options.map(o => {
            const v = String(o.value)
            return (
              <label key={v} className="config-multiselect-option" title={o.label}>
                <input
                  className="form-check-input"
                  type="checkbox"
                  checked={current.has(v)}
                  onChange={e => {
                    const next = options
                      .map(x => String(x.value))
                      .filter(x => (x === v ? e.target.checked : current.has(x)))
                    onChange(next)
                  }}
                />
                <span>{o.label}</span>
              </label>
            )
          })}
        </div>
      )}
    </div>
  )
}

/** 控件：与 widgets.py 的 put_arg_* 分支一一对应。 */
function ArgControl({ arg, onChange }: { arg: Arg; onChange: (v: any) => void }) {  if (arg.type === 'select' && arg.option.length) {
    return (
      <select className="form-control" value={arg.value ?? ''} onChange={e => onChange(e.target.value)}>
        {arg.option.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    )
  }
  if (arg.type === 'checkbox' || typeof arg.value === 'boolean') {
    return (
      <div className="form-check">
        <input
          className="form-check-input"
          type="checkbox"
          checked={!!arg.value}
          onChange={e => onChange(e.target.checked)}
        />
      </div>
    )
  }
  if (arg.type === 'datetime') {
    // 老 UI 就是普通文本框（widgets.py:1012 put_arg_datetime → 1018 put_input），
    // 用户可以随手输入、随时改，格式由后端 validate 校验。
    //
    // 这里绝对不能用 type="datetime-local"（2026-11-19 事故）：
    //   用户想输「2026」表达年份 → 浏览器直接判定非法值 → e.target.value 变空串
    //   → 被当成「清空」→ 触发立即运行 → 后端回写模板默认值 2020-01-01
    //   → 用户看到的是「我输入 2026 结果变成 2020 还报错」。
    // 文本框不会静默丢字符，输错了也能看见自己输的是什么。
    const str = String(arg.value ?? '')
    return (
      <input
        className="form-control"
        type="text"
        inputMode="numeric"
        placeholder="YYYY-MM-DD HH:MM:SS"
        value={str}
        onChange={e => onChange(e.target.value)}
      />
    )
  }
  if (arg.type === 'textarea') {
    // 「a > b > c」形式的优先级过滤器（如自定义旗舰航母过滤器 bogue > ranger >
    // langley > hermes）渲染成可拖拽排序列表 —— 老 UI task_priority 的同款交互，
    // 用户拖/点箭头即可调顺序，不用手写 > 分隔符（长卿 2026-11-17）。
    // 认不出的值（YAML / 多行 / 非 > 分隔 / LLM API Key 那种长串）退回普通 textarea。
    const v = String(arg.value ?? '')
    if (isPriorityList(v)) {
      return <PriorityFilter value={v} onChange={onChange} />
    }
    return (
      <textarea
        className="form-control config-textarea"
        // 老 UI 的 put_textarea 默认 rows=6（module/webui/pin.py:25），
        // 我原来写死 3 行，YAML 配置（推送 provider/key 那种）只能看到两三行，
        // 长卿 2026-11-17：「这个输入框怎么还是这种小框啊？不是叫你搞个长文本框吗」。
        rows={6}
        value={arg.value ?? ''}
        onChange={e => onChange(e.target.value)}
      />
    )
  }
  // 老 UI 的 task_priority 控件（widgets.py:639）：任务是固定的枚举，
  // 用「中文任务名 + 英文代号」双列可拖拽列表 —— 长卿截图里图二就是它
  // （跨月每日/OpsiCrossMonth、重启设置/Restart…）。
  // 后端已经把任务名翻译好了放在 option 里，这里直接用 labelOf 查表。
  if (arg.type === 'task_priority') {
    const nameMap: Record<string, string> = {}
    for (const o of arg.option || []) nameMap[String(o.value)] = o.label
    return (
      <PriorityFilter
        value={String(arg.value ?? '')}
        onChange={onChange}
        labelOf={(code) => nameMap[code] || code}
      />
    )
  }
  // 多选（船坞筛选的稀有度/附加索引、委托商店优先级等）：折叠成一个小框，
  // 点一下才展开全部选项（长卿 2026-11-21：「你别给全部直接摆出来呀…
  // 折叠到那个小框里面点一下全部再展开」）。实现见 MultiSelect。
  if (arg.type === 'multiselect') {
    return <MultiSelect arg={arg} onChange={onChange} />
  }
  return (
    <input className="form-control" type="text" value={arg.value ?? ''} onChange={e => onChange(e.target.value)} />
  )
}

/**
 * 参数容器的 scope id。
 *
 * ⚠️ textarea 必须用老 UI 那个**拼错的** id：`arg_contianer`（少一个 n），
 * 见 module/webui/widgets.py:631。这不是笔误，是必须复刻的契约：
 *
 *   alas-pc.css:1  [id^="pywebio-scope-arg_container-"] {
 *       grid-auto-flow: column;  grid-template-columns: 1fr 13rem;
 *   }
 *
 * 这条两列网格（左 1fr 说明 / 右 13rem 控件）是给下拉框、单行输入框用的。
 * 老 UI 的 textarea 容器拼成 `arg_contianer` → **匹配不上这条选择器** →
 * 没有两列网格 → textarea 自然占满整行。
 *
 * 我原来写成正确的 `arg_container-textarea-`，正好命中两列网格，textarea
 * 被塞进 208px 宽的右列，于是又窄又竖（长卿 2026-11-18 截图：
 * 「我的长条输入文本框呢？是TM横的 不是竖的」）。实测容器 909px、
 * 右列只有 208px。
 */
function scopeIdFor(kind: string, name: string): string {
  // 只有 textarea 沿用老 UI 的拼写错误，其余控件保持一致。
  // multiselect 也走正确前缀：index.tsx 保存失败时按
  // `[id^="pywebio-scope-arg_container-"]` 找容器加红框，拼错就标不上。
  const prefix = kind === 'textarea' ? 'arg_contianer' : 'arg_container'
  return `pywebio-scope-${prefix}-${kind}-${name}`
}

/** 单个参数块：#pywebio-scope-arg_container-{类型}-{参数名}。 */
export function ArgBlock({
  arg, onChange, onRunNow,
}: {
  arg: Arg
  onChange: (v: any) => void
  /** 传了就在控件下方渲染「立即运行」按钮（仅 Scheduler.NextRun 用）。 */
  onRunNow?: () => void
}) {
  // 点击后的短反馈（长卿 2026-11-19：「点完了之后没有任何反馈」）：
  // 1.2 秒内切到「正在触发…」并禁用，防止连点，也让用户确认点上了。
  const [running, setRunning] = useState(false)
  const fireRunNow = () => {
    if (!onRunNow || running) return
    setRunning(true)
    onRunNow()
    setTimeout(() => setRunning(false), 1200)
  }
  const kind =
    arg.type === 'select' ? 'select'
    : arg.type === 'checkbox' || typeof arg.value === 'boolean' ? 'checkbox'
    : arg.type === 'textarea' ? 'textarea'
    // 老 UI widget_type 有自己的 scope 名（widgets.py:1012 put_arg_datetime →
    // 'arg_container-datetime-{name}'）。必须区分出来，否则 NextRun 这类
    // 时间控件会和普通输入框共用一个 id 前缀，也不利于按类型做样式。
    : arg.type === 'datetime' ? 'datetime'
    : arg.type === 'multiselect' ? 'multiselect'
    : 'input'
  return (
    <div id={scopeIdFor(kind, arg.name)}>
      {/* 标题+帮助必须包在**一个** grid 项里：alas-pc.css 的
          [id^="pywebio-scope-arg_container-"] 是两列 grid（1fr 13rem），
          标题、帮助、控件若是 3 个直接子元素会被拆到 3 个格子里。 */}
      <div style={{ display: 'grid', gridAutoFlow: 'row', gridTemplateRows: 'auto 1fr' }}>
        <p style={{ whiteSpace: 'pre-wrap', ['--arg-title--' as string]: '1' } as React.CSSProperties}>
          {arg.title}
        </p>
        {arg.help && (
          <p style={{ whiteSpace: 'pre-wrap', ['--arg-help--' as string]: '1' } as React.CSSProperties}>
            {arg.help}
          </p>
        )}
      </div>
      {/* 老 UI put_arg_checkbox 的控件带 .style("text-align: center")
          （module/webui/widgets.py:1007）—— MD3 开关只有 52px 宽，在 13rem
          的控件列里不居中就会贴列左、离卡片右缘差 150+px，视觉上「悬在
          中间不靠边」（长卿 2026-11-19：「按钮往右边靠点…老UI都是靠边的」）。
          只对 checkbox 复刻这个 center，其他控件老 UI 没加。 */}
      <div
        style={{
          ['--input--' as string]: '1',
          ...(kind === 'checkbox' ? { textAlign: 'center' as const } : {}),
        }}
      >
        {onRunNow ? (
          // 「立即运行」：老 UI 是 NextRun 下方一行小字链接
          // （app_task_config.py:669-690，点击把 NextRun 置空触发调度器立即执行）。
          // 长卿 2026-11-19 要求做得更像音乐播放器的播放按钮，所以这里用
          // 圆形 ▶ 按钮 + 文字，点击后置空 NextRun。
          // 整行可点（长卿 2026-11-19：「为什么一定要点到球才它才可以立即运行？
          // 点那个立即运行那个字它没有反馈，点不动」）—— 用 <button> 包住球+文字，
          // 整块都是热区，鼠标移上去文字也会高亮。
          <button
            type="button"
            className={'run-now-row' + (running ? ' is-running' : '')}
            onClick={fireRunNow}
            disabled={running}
            title="立即运行该任务"
            aria-label="立即运行"
          >
            <span className="run-now-btn" aria-hidden="true">
              {running ? (
                <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true" className="run-now-spin">
                  <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2.4" strokeDasharray="14 42" strokeLinecap="round" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
                  <path d="M8 5v14l11-7z" fill="currentColor" />
                </svg>
              )}
            </span>
            <span className="run-now-text">{running ? '正在触发…' : '立即运行'}</span>
          </button>
        ) : null}
        <ArgControl arg={arg} onChange={onChange} />
      </div>
    </div>
  )
}

/**
 * 渲染一组配置卡 + 自动保存。
 *
 * 老 UI 没有保存按钮——控件改完由 pin_on_change 自动落盘，这里用 600ms debounce 对齐。
 */
export function ConfigGroups({
  groups: initial, name, task, onError,
}: {
  groups: Group[]; name: string; task: string; onError?: (msg: string) => void
}) {
  const [groups, setGroups] = useState<Group[]>(initial)

  // 父组件异步拿到 schema 后要同步进来（首帧 initial 是空数组）。
  //
  // 依赖不能用 [initial]：父组件每次渲染都会重新 map 出**新数组引用**，
  // 于是这个 effect 每帧都跑、把用户刚改的值重置回服务端值 —— 表现是
  // 复选框点了没反应、下拉框弹回去。这里只在「内容签名真的变了」时同步。
  const sig = JSON.stringify(initial)
  const sigRef = useRef('')
  useEffect(() => {
    if (sigRef.current === sig) return
    sigRef.current = sig
    setGroups(initial)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig])

  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingRef = useRef<Record<string, any>>({})

  const flush = async () => {
    const batch = pendingRef.current
    if (!Object.keys(batch).length) return
    pendingRef.current = {}
    try {
      const res = await fetch(`/newapi/config/${instSeg(name)}/task/${encodeURIComponent(task)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modified: batch }),
      })
      // ⚠️ 先判断 HTTP 状态再 parse：500 时后端返回 "Internal Server Error"
      // 纯文本，直接 res.json() 会抛 SyntaxError，把真实原因（HTTP 500）盖掉
      // —— 长卿截图里「Unexpected token 'I'」就是这么来的。
      if (!res.ok) {
        onError?.(`保存失败: HTTP ${res.status}`)
        return
      }
      const j = await res.json().catch(() => null)
      if (!j) {
        onError?.('保存失败: 后端返回了无法解析的内容')
        return
      }
      if (j.error) {
        onError?.('保存失败: ' + j.error)
        return
      }
      if (j.invalid?.length) {
        onError?.(`${j.valid?.length ?? 0} 项已保存，${j.invalid.length} 项校验失败`)
      } else {
        onError?.('')
      }
    } catch (e) {
      onError?.('保存失败: ' + String(e))
    }
  }

  const setArg = (group: string, argName: string, value: any) => {
    setGroups(gs => gs.map(g => g.group !== group ? g : {
      ...g,
      args: g.args.map(a => a.name !== argName ? a : { ...a, value }),
    }))
    // 键契约 = 老 UI _save_config 的三段全路径 Task.Group.Arg（args.json 三层）。
        // 两段键在 group 与 task 不同名时（如 General.Log.*）会写错层级。
        pendingRef.current = { ...pendingRef.current, [`${task}.${group}.${argName}`]: value }
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => { void flush() }, 600)
  }

  return (
    <>
      {groups.map(g => (
        <div key={g.group} id={`pywebio-scope-group_${g.group}`}>
          <p style={{ whiteSpace: 'pre-wrap' }}>{g.title || g.group}</p>
          <hr className="hr-group" />
          <div id={`pywebio-scope-group_${g.group}_body`}>
            {g.args.map(a => (
              <ArgBlock
                key={a.name}
                arg={a}
                onChange={v => setArg(g.group, a.name, v)}
                // Scheduler 组的 NextRun 带「立即运行」：置空即触发调度器立即执行
                // （老 UI app_task_config.py:669-690 同款语义）。
                onRunNow={
                  g.group === 'Scheduler' && a.name === 'NextRun'
                    ? () => {
                        setGroups(gs => gs.map(gg => gg.group !== g.group ? gg : {
                          ...gg,
                          args: gg.args.map(x => x.name !== a.name ? x : { ...x, value: '' }),
                        }))
                        pendingRef.current = { ...pendingRef.current, [`${task}.${g.group}.${a.name}`]: '' }
                        if (saveTimer.current) clearTimeout(saveTimer.current)
                        // 立即保存，不等 600ms debounce：用户期望「点一下就跑」
                        void flush()
                      }
                    : undefined
                }
              />
            ))}
          </div>
        </div>
      ))}
    </>
  )
}