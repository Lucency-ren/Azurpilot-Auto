// 调度器启停条（老 UI alas_daemon_overview 的 scheduler-bar，app_overview.py:506-543）。
//
// 老 UI 只有 page=tool 的任务页带这条栏，普通任务的配置页（alas_set_group）没有。
// 但用户点「工具」里的任务、以及在配置页想直接开跑时，找不到启动按钮 ——
// 于是把这个条抽成组件，配置页与工具页共用：
//   div#pywebio-scope-scheduler-bar
//     ├─ span「调度器」
//     └─ div#pywebio-scope-scheduler_btn
//          └─ button.btn.btn-on|btn-off   (启动 / 停止)
//
// DOM id 必须与老 CSS（alas.css:759-778）对齐，否则没有卡片外观。
import { useEffect, useState } from 'react'
import { apiGet, instSeg } from '../api/client'
import { putText } from '../lib/pywebio'

type OverviewResp = { alive: boolean }

export function SchedulerBar({ instance }: { instance: string }) {
  const [alive, setAlive] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  // 与总览页同一周期轮询，避免两边状态不一致
  useEffect(() => {
    let mounted = true
    const load = () => {
      apiGet<OverviewResp>('/newapi/overview/' + instSeg(instance))
        .then(r => { if (mounted) setAlive(!!r.alive) })
        .catch(() => { /* 后端重启中，忽略 */ })
    }
    load()
    const t = setInterval(load, 15000)
    return () => { mounted = false; clearInterval(t) }
  }, [instance])

  const toggle = async () => {
    setBusy(true)
    setErr('')
    try {
      await fetch(`/newapi/scheduler/${instSeg(instance)}/${alive ? 'stop' : 'start'}`, { method: 'POST' })
      // 立刻读回，不等 15s 轮询，否则按钮像没反应
      const next = await apiGet<OverviewResp>('/newapi/overview/' + instSeg(instance)).catch(() => null)
      if (next) setAlive(!!next.alive)
    } catch (e) {
      setErr('调度器操作失败: ' + String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div id="pywebio-scope-scheduler-bar">
      <span
        dangerouslySetInnerHTML={{
          __html: putText('调度器', ';;font-size: 1.25rem; margin: auto .5rem auto;'),
        }}
      />
      <div id="pywebio-scope-scheduler_btn">
        <div>
          <button
            className={'btn ' + (alive ? 'btn-off' : 'btn-on')}
            disabled={busy}
            onClick={toggle}
            title={err || (alive ? '停止当前调度器' : '启动调度器')}
          >
            {alive ? '停止' : '启动'}
          </button>
        </div>
      </div>
    </div>
  )
}
