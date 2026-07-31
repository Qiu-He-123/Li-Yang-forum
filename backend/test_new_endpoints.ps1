$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:8765"

Add-Type -AssemblyName System.Net.Http
$handler = New-Object System.Net.Http.HttpClientHandler
$handler.CookieContainer = New-Object System.Net.CookieContainer
$client = New-Object System.Net.Http.HttpClient($handler)
$client.Timeout = [TimeSpan]::FromSeconds(30)

# Login first
$body = @{phone="13900000001"; password="test12345"} | ConvertTo-Json
$content = New-Object System.Net.Http.StringContent($body, [System.Text.Encoding]::UTF8, "application/json")
$resp = $client.PostAsync("$base/auth/login", $content).Result
$loginResult = $resp.Content.ReadAsStringAsync().Result
Write-Host "[LOGIN] $loginResult"

function Send-Req {
    param([string]$method, [string]$path, [string]$body = "", [string]$desc)
    Write-Host ""
    Write-Host "========== $desc =========="
    try {
        $url = "$base$path"
        $payload = $body
        if ([string]::IsNullOrEmpty($payload)) { $payload = "{}" }
        if ($method -eq "GET") {
            $r = $client.GetAsync($url).Result
        } elseif ($method -eq "POST") {
            $c = New-Object System.Net.Http.StringContent($payload, [System.Text.Encoding]::UTF8, "application/json")
            $r = $client.PostAsync($url, $c).Result
        } elseif ($method -eq "PATCH") {
            $c = New-Object System.Net.Http.StringContent($payload, [System.Text.Encoding]::UTF8, "application/json")
            $r = $client.PatchAsync($url, $c).Result
        } elseif ($method -eq "DELETE") {
            $r = $client.DeleteAsync($url).Result
        } else {
            $r = $client.GetAsync($url).Result
        }
        $text = $r.Content.ReadAsStringAsync().Result
        $json = $text | ConvertFrom-Json
        Write-Host "code=$($json.code) msg=$($json.msg)"
        $dataStr = $json.data | ConvertTo-Json -Depth 8 -Compress
        if ($dataStr -and $dataStr.Length -gt 800) {
            $dataStr = $dataStr.Substring(0, 800) + "..."
        }
        Write-Host "data: $dataStr"
    } catch {
        Write-Host "[ERROR] $($_.Exception.Message)"
    }
}

Send-Req -method "GET" -path "/circles" -desc "1. GET /circles"
Send-Req -method "GET" -path "/circles/default" -desc "2. GET /circles/default"
Send-Req -method "POST" -path "/circles/default/join" -desc "3. POST /circles/default/join"
Send-Req -method "GET" -path "/circles/default/posts" -desc "4. GET /circles/default/posts"
Send-Req -method "GET" -path "/search/hot" -desc "5. GET /search/hot"
Send-Req -method "GET" -path "/posts?q=test" -desc "6. GET /posts?q=test"
Send-Req -method "GET" -path "/search/history" -desc "7. GET /search/history"
Send-Req -method "GET" -path "/users/me" -desc "8. GET /users/me"
Send-Req -method "GET" -path "/users/1" -desc "9. GET /users/1"
Send-Req -method "POST" -path "/users/1/follow" -desc "10. POST /users/1/follow"
Send-Req -method "GET" -path "/users/1/is-following" -desc "11. GET /users/1/is-following"
Send-Req -method "GET" -path "/users/24/following" -desc "12. GET /users/24/following"
Send-Req -method "GET" -path "/users/1/followers" -desc "13. GET /users/1/followers"
Send-Req -method "GET" -path "/notifications?type=follow" -desc "14. GET /notifications?type=follow"
Send-Req -method "GET" -path "/notifications" -desc "15. GET /notifications"
Send-Req -method "GET" -path "/notifications/unread-count" -desc "16. GET /notifications/unread-count"
Send-Req -method "GET" -path "/posts?page=1&page_size=1" -desc "17. GET /posts list"
Send-Req -method "POST" -path "/posts/1/view" -desc "18. POST /posts/1/view"
Send-Req -method "POST" -path "/posts/1/share" -desc "19. POST /posts/1/share"
Send-Req -method "GET" -path "/posts/1/related" -desc "20. GET /posts/1/related"
Send-Req -method "PATCH" -path "/notifications/read-all?type=follow" -desc "21. PATCH read-all?type=follow"
Send-Req -method "PATCH" -path "/notifications/read-all" -desc "22. PATCH read-all"
Send-Req -method "DELETE" -path "/search/history" -desc "23. DELETE /search/history"
Send-Req -method "DELETE" -path "/circles/default/join" -desc "24. DELETE /circles/default/join"
Send-Req -method "DELETE" -path "/users/1/follow" -desc "25. DELETE /users/1/follow"

Write-Host ""
Write-Host "========== All tests completed =========="
