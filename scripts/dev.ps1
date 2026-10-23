<#
.SYNOPSIS
  MetricMind 本地一键启动 / 停止脚本（Windows PowerShell 5.1+）。

.DESCRIPTION
  1. 自动找可用的 Python：优先 backend\.venv\Scripts\python.exe，其次 PATH 里的 python；
  2. 自动找 Node：PATH -> 常见安装路径 -> 本机 DSH 运行时（仅作兜底）；
  3. 端口已健康则跳过；端口被别的进程占用时给出明确提示（uvicorn 的 "Aborted!" 就是这种情况）；
  4. 日志写到 .dev-logs\，PID 写到 .dev-pids.json，方便 -Stop。

.EXAMPLE
  .\scripts\dev.ps1            # 启动前后端
  .\scripts\dev.ps1 -WebOnly   # 只启动前端
  .\scripts\dev.ps1 -Stop      # 停止本脚本启动的进程
#>
param(
    [switch]$ApiOnly,
    [switch]$WebOnly,
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root '.dev-pids.json'
$logDir = Join-Path $root '.dev-logs'
$backendDir = Join-Path $root 'backend'
$frontendDir = Join-Path $root 'frontend'

function Test-PortOpen([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync('127.0.0.1', $Port)
        if (-not $task.Wait(400)) { return $false }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Start-DetachedProcess {
    <#
      启动一个后台进程并重定向日志。
      为什么不用裸 Start-Process：某些启动器（IDE / 沙箱 / CI 包装器）会同时注入
      http_proxy 与 HTTP_PROXY，PowerShell 枚举环境变量时把它们当成两个同名键，
      Start-Process 复制环境就会抛 "已添加项。字典中的关键字..."，服务根本起不来。
      这种情况下退回 WMI Win32_Process.Create：它按原始环境块创建进程，不做字典复制。
    #>
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [string]$StdOut,
        [string]$StdErr
    )

    try {
        return Start-Process -FilePath $FilePath -ArgumentList $Arguments `
            -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $StdOut -RedirectStandardError $StdErr -ErrorAction Stop
    } catch {
        Write-Host ("Start-Process 失败（{0}），改用 WMI 创建进程。" -f $_.Exception.Message) -ForegroundColor DarkYellow
        $quoted = ($Arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
        $redirect = ''
        if ($StdOut) { $redirect += (' > "{0}"' -f $StdOut) }
        if ($StdErr) { $redirect += (' 2> "{0}"' -f $StdErr) }
        $commandLine = 'cmd /c ""{0}" {1}{2}""' -f $FilePath, $quoted, $redirect
        $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine      = $commandLine
            CurrentDirectory = $WorkingDirectory
        }
        if ($result.ReturnValue -ne 0) {
            throw ('WMI 创建进程失败，ReturnValue={0}' -f $result.ReturnValue)
        }
        return [pscustomobject]@{ Id = [int]$result.ProcessId }
    }
}

function Test-ApiHealthy {
    try {
        $response = Invoke-WebRequest 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Resolve-Python {
    $venv = Join-Path $backendDir '.venv\Scripts\python.exe'
    if (Test-Path $venv) { return $venv }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Resolve-Node {
    $cmd = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'),
        (Join-Path $env:ProgramFiles 'nodejs\node.exe')
    )
    if (${env:ProgramFiles(x86)}) { $candidates += (Join-Path ${env:ProgramFiles(x86)} 'nodejs\node.exe') }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    return $null
}

function Resolve-ViteRunner([string]$NodePath) {
    $vite = Join-Path $frontendDir 'node_modules\vite\bin\vite.js'
    if (-not (Test-Path $vite)) { return $null }
    return $vite
}

if ($Stop) {
    if (-not (Test-Path $pidFile)) {
        Write-Host '没有找到 .dev-pids.json：请确认是用本脚本启动的服务。' -ForegroundColor Yellow
        exit 0
    }
    $saved = Get-Content $pidFile -Raw | ConvertFrom-Json
    foreach ($entry in @($saved.api, $saved.web)) {
        if ($entry -and $entry.pid) {
            try {
                Stop-Process -Id $entry.pid -Force -ErrorAction Stop
                Write-Host ("已停止 {0}（PID {1}）" -f $entry.name, $entry.pid) -ForegroundColor Green
            } catch {
                Write-Host ("进程 {0} 已不存在" -f $entry.pid) -ForegroundColor DarkGray
            }
        }
    }
    # WMI 兜底启动时，pid 文件记录的是 cmd 包装进程，真正的监听进程要按端口找
    foreach ($port in @(8000, 5173)) {
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object {
                try {
                    Stop-Process -Id $_.OwningProcess -Force -ErrorAction Stop
                    Write-Host ("已停止占用 {0} 的进程（PID {1}）" -f $port, $_.OwningProcess) -ForegroundColor Green
                } catch { }
            }
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    exit 0
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$started = [ordered]@{}

# ---------- backend ----------
if (-not $WebOnly) {
    if (Test-PortOpen 8000) {
        if (Test-ApiHealthy) {
            Write-Host '后端已在 8000 运行（/api/health 正常），跳过启动。' -ForegroundColor DarkGray
        } else {
            Write-Host '端口 8000 被占用但不是 MetricMind 后端。请先结束占用进程（下面可查 PID）：' -ForegroundColor Red
            Write-Host '  netstat -ano | findstr :8000' -ForegroundColor Yellow
            exit 1
        }
    } else {
        $python = Resolve-Python
        if (-not $python) {
            Write-Host '找不到 Python。请安装 Python 3.11+ 或先创建 backend\.venv。' -ForegroundColor Red
            exit 1
        }
        $apiLog = Join-Path $logDir 'api.log'
        $apiErr = Join-Path $logDir 'api.err.log'
        $api = Start-DetachedProcess -FilePath $python `
            -Arguments @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') `
            -WorkingDirectory $backendDir -StdOut $apiLog -StdErr $apiErr
        $started['api'] = @{ name = 'api'; pid = $api.Id; log = $apiLog }
        Write-Host ("后端启动中（PID {0}），日志：{1}" -f $api.Id, $apiLog) -ForegroundColor Green
    }
}

# ---------- frontend ----------
if (-not $ApiOnly) {
    if (Test-PortOpen 5173) {
        Write-Host '前端已在 5173 运行，跳过启动。' -ForegroundColor DarkGray
    } else {
        $node = Resolve-Node
        if (-not $node) {
            Write-Host '找不到 Node.js。请安装 Node 18+（https://nodejs.org），或在具备 Node 的终端里运行。' -ForegroundColor Red
            Write-Host '装好 Node 后仍需在 frontend 目录执行一次：pnpm install' -ForegroundColor Yellow
            exit 1
        }
        $vite = Resolve-ViteRunner $node
        if (-not $vite) {
            Write-Host 'frontend\node_modules 不存在。请先安装依赖：' -ForegroundColor Red
            Write-Host '  cd frontend' -ForegroundColor Yellow
            Write-Host '  pnpm install    # 或 npm install' -ForegroundColor Yellow
            exit 1
        }
        $webLog = Join-Path $logDir 'web.log'
        $webErr = Join-Path $logDir 'web.err.log'
        $web = Start-DetachedProcess -FilePath $node `
            -Arguments @($vite, '--host', '127.0.0.1', '--port', '5173') `
            -WorkingDirectory $frontendDir -StdOut $webLog -StdErr $webErr
        $started['web'] = @{ name = 'web'; pid = $web.Id; log = $webLog }
        Write-Host ("前端启动中（PID {0}），日志：{1}" -f $web.Id, $webLog) -ForegroundColor Green
    }
}

if ($started.Count -gt 0) {
    $payload = [ordered]@{}
    foreach ($key in $started.Keys) { $payload[$key] = $started[$key] }
    ($payload | ConvertTo-Json -Depth 4) | Set-Content -Path $pidFile -Encoding UTF8
}

Start-Sleep -Seconds 2
Write-Host ''
if (Test-ApiHealthy) {
    Write-Host '后端  http://127.0.0.1:8000/api/health  OK' -ForegroundColor Green
} elseif (-not $WebOnly) {
    Write-Host '后端还在启动，稍等几秒再刷新；若持续失败请看 .dev-logs\api.err.log' -ForegroundColor Yellow
}
if (Test-PortOpen 5173) {
    Write-Host '前端  http://127.0.0.1:5173  OK' -ForegroundColor Green
} elseif (-not $ApiOnly) {
    Write-Host '前端还在启动；若持续失败请看 .dev-logs\web.err.log' -ForegroundColor Yellow
}
Write-Host ''
Write-Host '停止：.\scripts\dev.ps1 -Stop' -ForegroundColor DarkGray
