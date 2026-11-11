# Connect to qbox_db using credentials configured in backend/.env
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Error "Could not find .env file in $PSScriptRoot"
    exit 1
}

$syncUrlLine = (Get-Content $envFile | Select-String "^DATABASE_SYNC_URL=").Line
if ($syncUrlLine -match '://qbox_app:(?<pass>[^@]+)@(?<host>[^:/]+)(:(?<port>\d+))?/(?<db>[^\s?]+)') {
    $env:PGPASSWORD = $Matches['pass']
    $hostName = $Matches['host']
    $port = if ($Matches['port']) { $Matches['port'] } else { '5432' }
    $dbName = $Matches['db']
    
    Write-Host "Connecting to PostgreSQL database '$dbName' as 'qbox_app'..." -ForegroundColor Cyan
    & psql -U qbox_app -h $hostName -p $port -d $dbName @args
} else {
    Write-Error "Could not parse DATABASE_SYNC_URL from .env"
}
