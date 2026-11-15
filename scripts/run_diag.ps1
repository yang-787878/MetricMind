<#
.SYNOPSIS
  MetricMind 运行诊断：回答「上一次问答为什么失败、卡在哪一步」。

.DESCRIPTION
  为什么需要它：Docker 日志只有 INFO 级的 HTTP 请求行和 run_created / run_finalized
  两个标记，工具调用失败（tool_call_failed）、预算耗尽、重规划原因都只在事件流里，
  不在 stdout。也就是说 `docker compose logs` 看得到「这次运行挂了」，看不到「为什么挂」。

  真正的「报错日志」是每次运行的事件流，已经落在 SQLite 里、也由 API 暴露：
    GET /api/runs                → 最近运行列表（含 status）
    GET /api/runs/{id}           → 结构化终态：error / steps[].tool_calls[].error / warnings
    GET /api/runs/{id}/events    → 完整时间线（run_created → tool_call_failed → replan → run_failed）

  本脚本把这三者拼成一个可读的失败链，不需要 jq、不需要进容器。

.PARAMETER RunId
  指定 run_id 打印详细失败链；省略时只列最近的运行。

.PARAMETER Limit
  列表条数，默认 10。

.PARAMETER FailedOnly
  只显示 failed / partial 的运行。

.PARAMETER Timeline
  在详情里打印完整事件时间线（默认只打印失败、重规划、预算相关事件）。

.PARAMETER Api
  API 基地址，默认本机 Docker 映射端口 http://127.0.0.1:18000。

.EXAMPLE
  .\scripts\run_diag.ps1
  .\scripts\run_diag.ps1 -RunId run_ae748ee08183461d872c
  .\scripts\run_diag.ps1 -FailedOnly -Timeline
#>
param(
    [string]$RunId,
    [int]$Limit = 10,
    [switch]$FailedOnly,
    [switch]$Timeline,
    [string]$Api = 'http://127.0.0.1:18000'
)

$ErrorActionPreference = 'Stop'
$Api = $Api.TrimEnd('/')

# PS 5.1 的 Invoke-RestMethod 会按 ISO-8859-1 解码 JSON，中文变乱码；
# 这里显式按 UTF-8 解字节，避免「错误信息本身看不懂」。
function Get-ApiJson([string]$Path) {
    $client = New-Object System.Net.WebClient
    try {
        $bytes = $client.DownloadData("$Api$Path")
    } finally {
        $client.Dispose()
    }
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    return $text | ConvertFrom-Json
}

function Format-LocalTime([string]$Iso) {
    if (-not $Iso) { return '-' }
    try {
        return ([datetime]::Parse($Iso)).ToLocalTime().ToString('MM-dd HH:mm:ss')
    } catch {
        return $Iso
    }
}

function Write-Section([string]$Title) {
    Write-Host ''
    Write-Host "== $Title ==" -ForegroundColor Cyan
}

function Write-RunList {
    $data = Get-ApiJson "/api/runs?limit=$Limit"
    $items = @($data.items)
    if ($FailedOnly) {
        $items = @($items | Where-Object { $_.status -in @('failed', 'partial') })
    }
    Write-Section "最近 $($items.Count) 次运行（$Api）"
    if ($items.Count -eq 0) {
        Write-Host '  没有匹配的运行。' -ForegroundColor DarkGray
        return
    }
    foreach ($run in $items) {
        $color = switch ($run.status) {
            'succeeded' { 'Green' }
            'partial' { 'Yellow' }
            'failed' { 'Red' }
            default { 'Gray' }
        }
        $line = '{0}  {1,-9}  {2}  {3}' -f $run.run_id, $run.status, (Format-LocalTime $run.created_at), $run.question
        Write-Host $line -ForegroundColor $color
    }
    $failed = @($items | Where-Object { $_.status -eq 'failed' })
    if ($failed.Count -gt 0) {
        Write-Host ''
        Write-Host "看失败原因：.\scripts\run_diag.cmd -RunId $($failed[0].run_id)" -ForegroundColor DarkGray
    }
}

function Write-RunDetail([string]$Id) {
    $run = Get-ApiJson "/api/runs/$Id"

    Write-Section "运行 $Id"
    Write-Host "问题:  $($run.question)"
    Write-Host ("状态:  {0}    模式: {1}    模型: {2}    耗时: {3}s" -f `
        $run.status, $run.mode, $run.model, [math]::Round(($run.duration_ms / 1000.0), 1))
    Write-Host ("预算:  步骤 {0}/{1}  工具 {2}/{3}  重规划 {4}/{5}" -f `
        $run.usage.steps_used, $run.budget.max_steps, `
        $run.usage.tool_calls_used, $run.budget.max_tool_calls, `
        $run.usage.replans_used, $run.budget.max_replans)

    if ($run.error) {
        Write-Host ''
        Write-Host "终态错误: $($run.error.code)" -ForegroundColor Red
        Write-Host "  $($run.error.message)"
        if ($run.error.hint) { Write-Host "  提示: $($run.error.hint)" -ForegroundColor DarkYellow }
    }

    Write-Section '步骤与工具调用'
    foreach ($step in @($run.steps)) {
        $color = switch ($step.status) {
            'succeeded' { 'Green' }
            'skipped' { 'Yellow' }
            'failed' { 'Red' }
            default { 'Gray' }
        }
        Write-Host ('  {0} {1,-18} {2,-10} {3}' -f $step.step_id, $step.tool, $step.status, $step.summary) -ForegroundColor $color
        foreach ($call in @($step.tool_calls)) {
            if ($call.error) {
                Write-Host ("      └ {0} {1} ({2}ms): {3}" -f `
                    $call.call_id, $call.error.code, $call.duration_ms, $call.error.message) -ForegroundColor Red
                if ($call.error.hint) {
                    Write-Host "        hint: $($call.error.hint)" -ForegroundColor DarkYellow
                }
                # 参数摘要能区分「模型写错了参数」和「服务端没注入参数」，是定位根因的关键
                Write-Host ("        args: " + (($call.arguments | ConvertTo-Json -Compress -Depth 6) -replace '\s+', ' ')) -ForegroundColor DarkGray
            }
        }
    }

    if (@($run.warnings).Count -gt 0) {
        Write-Section '警告'
        foreach ($warning in @($run.warnings)) { Write-Host "  - $warning" -ForegroundColor Yellow }
    }

    Write-Section '事件时间线'
    $events = Get-ApiJson "/api/runs/$Id/events?after_seq=0&limit=500"
    $interesting = @('run_created', 'run_started', 'dataset_inspected', 'plan_created', 'replan_requested',
        'budget_warning', 'run_succeeded', 'run_failed', 'run_cancelled', 'report_created')
    foreach ($event in @($events.events)) {
        $isError = $event.type -match 'failed|error'
        $isNoise = $event.type -match '^tool_call_succeeded|^step_started|^step_completed|^evidence_recorded'
        if (-not $Timeline -and $isNoise) { continue }
        if (-not $Timeline -and -not $isError -and $event.type -notin $interesting) { continue }

        $payload = $event.payload
        $detail = switch ($event.type) {
            'tool_call_failed' { "$($payload.tool): $($payload.error.code) — $($payload.error.message)" }
            'step_completed' { "$($payload.step_id) $($payload.status) $($payload.summary)" }
            'tool_call_started' { "$($payload.tool) $((($payload.args_summary | ConvertTo-Json -Compress -Depth 4) -replace '\s+', ' '))" }
            'replan_requested' { "第 $($payload.replan_count) 次重规划：$($payload.reason)" }
            'budget_warning' { "$($payload.kind) 已用 $($payload.used)/$($payload.limit)" }
            'run_failed' { "status=$($payload.status) error=$($payload.error.code) $($payload.error.message)" }
            'run_succeeded' { "status=$($payload.status)" }
            default { '' }
        }
        $color = if ($isError) { 'Red' } elseif ($event.type -match 'replan|budget') { 'Yellow' } else { 'Gray' }
        Write-Host ('  {0} #{1,-3} {2,-20} {3}' -f (Format-LocalTime $event.ts), $event.seq, $event.type, $detail) -ForegroundColor $color
    }
}

try {
    if ($RunId) {
        Write-RunDetail $RunId
    } else {
        Write-RunList
    }
} catch [System.Net.WebException] {
    Write-Host "连不上 API（$Api）：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host '容器没起？先在 D:\work\MetricMind 执行: docker compose up -d' -ForegroundColor DarkGray
    Write-Host '只想看容器日志: docker compose logs --tail 200 api' -ForegroundColor DarkGray
    exit 1
}
