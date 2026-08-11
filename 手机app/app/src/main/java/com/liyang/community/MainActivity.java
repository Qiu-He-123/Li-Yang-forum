package com.liyang.community;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.text.Html;
import android.view.KeyEvent;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 立洋社区套壳 WebView。
 * - 打开 APP_URL 指向的网页（网址写在下面常量里，不用 strings.xml）；
 * - 启动时检查系统 WebView 内核版本，过低则提示更新；
 * - 打开 App 先拉取微云笔记公告；服务器连不上 / 返回 5xx 时显示维护面板；
 *   公告用"取中间文本"方式解析 标签{内容} 字段，取不到就提示检查网络；
 * - 联系管理员 = 复制 CONTACT_QQ，退出 = 关闭 App。
 */
public class MainActivity extends Activity {

    private static final int REQUEST_FILE_CHOOSER = 1001;
    /** 内核主版本号低于该值就提示更新（Chromium 100 ≈ 2022 年的内核） */
    private static final int MIN_WEBVIEW_MAJOR = 100;
    /** 要打开的网页地址（改这里即可，不用 strings.xml） */
    private static final String APP_URL = "https://al.u3593529.nyat.app:32449";
    /** 微云公告分享页 */
    private static final String NOTICE_URL = "https://share.weiyun.com/SpmKBnmC";
    /** 联系管理员按钮复制的 QQ 号 */
    private static final String CONTACT_QQ = "qhqe2623655749";
    /** 公告取不出来时显示的兜底文案 */
    private static final String DEFAULT_NOTICE = "请检查网络连接是否正常以及联系管理员";

    private WebView webView;
    private ProgressBar progressBar;
    private View offlinePanel;
    private View kernelPanel;
    private TextView noticeText;
    private String latestNotice;
    private boolean noticeFetching;
    private ValueCallback<Uri[]> filePathCallback;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Android 15+ 默认强制 edge-to-edge，网页内容会顶到刘海/摄像头区域。
        // 这里恢复"内容在系统状态栏下方"的传统布局，避免网站顶部被摄像头遮挡。
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            getWindow().setDecorFitsSystemWindows(true);
        }

        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webView);
        progressBar = findViewById(R.id.progressBar);
        offlinePanel = findViewById(R.id.offlinePanel);
        kernelPanel = findViewById(R.id.kernelPanel);
        noticeText = findViewById(R.id.noticeText);

        setupWebView();
        setupPanels();

        // 打开 App 先加载微云笔记公告（服务器挂了时维护面板直接显示）
        fetchNotice();

        // 内核太旧就先提示更新，避免打开一个渲染异常的页面
        if (isWebViewOutdated()) {
            showKernelPanel();
        } else {
            webView.loadUrl(APP_URL);
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void setupWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setSupportMultipleWindows(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        // 自定义 UA 标记：前端可用 navigator.userAgent.includes('LYCommunityApp') 区分 App 和网页版
        settings.setUserAgentString(
                WebSettings.getDefaultUserAgent(this) + " LYCommunityApp/1.0");

        CookieManager.getInstance().setAcceptCookie(true);
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.LOLLIPOP) {
            CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);
        }

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String host = uri.getHost();
                String appHost = Uri.parse(APP_URL).getHost();
                if (host != null && host.equals(appHost)) {
                    return false; // 站内链接留在 App 里打开
                }
                // 站外链接（微信/支付宝/浏览器等）交给系统处理
                try {
                    view.getContext().startActivity(new Intent(Intent.ACTION_VIEW, uri));
                } catch (ActivityNotFoundException ignored) {
                    // 没有能处理该链接的应用，忽略
                }
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                progressBar.setVisibility(View.GONE);
            }

            @Override
            public void onReceivedError(
                    WebView view, WebResourceRequest request, WebResourceError error) {
                // 主页面加载失败（断网、服务器没启动、域名失效等）→ 维护面板
                if (request.isForMainFrame()) {
                    showOffline();
                }
            }

            @Override
            public void onReceivedHttpError(
                    WebView view, WebResourceRequest request, WebResourceResponse errorResponse) {
                // 服务器返回 5xx（网关错误、服务异常）→ 维护面板
                if (request.isForMainFrame() && errorResponse.getStatusCode() >= 500) {
                    showOffline();
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                if (newProgress < 100) {
                    progressBar.setVisibility(View.VISIBLE);
                    progressBar.setProgress(newProgress);
                } else {
                    progressBar.setVisibility(View.GONE);
                }
            }

            @Override
            public boolean onShowFileChooser(
                    WebView webView,
                    ValueCallback<Uri[]> filePathCallback,
                    FileChooserParams fileChooserParams) {
                if (MainActivity.this.filePathCallback != null) {
                    MainActivity.this.filePathCallback.onReceiveValue(null);
                }
                MainActivity.this.filePathCallback = filePathCallback;

                Intent intent = fileChooserParams.createIntent();
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                try {
                    startActivityForResult(
                            Intent.createChooser(intent, "选择文件"),
                            REQUEST_FILE_CHOOSER);
                } catch (ActivityNotFoundException e) {
                    MainActivity.this.filePathCallback.onReceiveValue(null);
                    MainActivity.this.filePathCallback = null;
                    return false;
                }
                return true;
            }
        });
    }

    private void setupPanels() {
        findViewById(R.id.btnRetry).setOnClickListener(v -> retryLoad());
        findViewById(R.id.btnContact).setOnClickListener(v -> copyContact());
        findViewById(R.id.btnExit).setOnClickListener(v -> exitApp());
        findViewById(R.id.btnUpdateKernel).setOnClickListener(v -> openWebViewUpdate());
        findViewById(R.id.btnUseAnyway).setOnClickListener(v -> {
            hidePanels();
            webView.loadUrl(APP_URL);
        });
    }

    // ---------- 内核版本检查 ----------

    private boolean isWebViewOutdated() {
        PackageInfo pkg = WebView.getCurrentWebViewPackage();
        if (pkg == null) {
            return true;
        }
        int major = 0;
        if (pkg.versionName != null) {
            Matcher m = Pattern.compile("(\\d+)").matcher(pkg.versionName);
            if (m.find()) {
                try {
                    major = Integer.parseInt(m.group(1));
                } catch (NumberFormatException ignored) {
                    // 解析失败按旧版处理
                }
            }
        }
        return major < MIN_WEBVIEW_MAJOR;
    }

    private void showKernelPanel() {
        PackageInfo pkg = WebView.getCurrentWebViewPackage();
        TextView versionText = findViewById(R.id.kernelVersionText);
        if (pkg != null) {
            versionText.setText("当前内核：\n" + pkg.packageName + "\n版本：" + pkg.versionName);
        } else {
            versionText.setText("未检测到可用的 WebView 内核");
        }
        webView.setVisibility(View.GONE);
        offlinePanel.setVisibility(View.GONE);
        kernelPanel.setVisibility(View.VISIBLE);
    }

    private void openWebViewUpdate() {
        Intent intent = new Intent(
                Intent.ACTION_VIEW, Uri.parse("market://details?id=com.google.android.webview"));
        try {
            startActivity(intent);
        } catch (ActivityNotFoundException e) {
            try {
                startActivity(new Intent(
                        Intent.ACTION_VIEW,
                        Uri.parse("https://play.google.com/store/apps/details?id=com.google.android.webview")));
            } catch (ActivityNotFoundException ignored) {
                Toast.makeText(
                                this,
                                "请在应用商店搜索「Android System WebView」并更新",
                                Toast.LENGTH_LONG)
                        .show();
            }
        }
    }

    // ---------- 维护面板 ----------

    private void showOffline() {
        progressBar.setVisibility(View.GONE);
        webView.setVisibility(View.GONE);
        kernelPanel.setVisibility(View.GONE);
        offlinePanel.setVisibility(View.VISIBLE);
        // 已有公告直接用；没有就先显示兜底文案，再补拉一次
        noticeText.setText(latestNotice != null ? latestNotice : DEFAULT_NOTICE);
        if (latestNotice == null) {
            fetchNotice();
        }
    }

    private void hidePanels() {
        offlinePanel.setVisibility(View.GONE);
        kernelPanel.setVisibility(View.GONE);
        webView.setVisibility(View.VISIBLE);
        progressBar.setVisibility(View.GONE);
    }

    private void retryLoad() {
        hidePanels();
        if (webView.getUrl() == null) {
            webView.loadUrl(APP_URL);
        } else {
            webView.reload();
        }
    }

    private void copyContact() {
        String qq = CONTACT_QQ;
        ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        cm.setPrimaryClip(ClipData.newPlainText("qq", qq));
        Toast.makeText(this, "QQ 号已复制：" + qq, Toast.LENGTH_SHORT).show();
    }

    private void exitApp() {
        finishAndRemoveTask();
    }

    // ---------- 微云公告拉取 ----------

    private void fetchNotice() {
        if (noticeFetching) {
            return;
        }
        noticeFetching = true;

        new Thread(() -> {
            String text = null;
            try {
                URL url = new URL(NOTICE_URL);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(8000);
                conn.setReadTimeout(8000);
                conn.setRequestMethod("GET");
                conn.setRequestProperty(
                        "User-Agent",
                        "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                                + "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36");
                conn.setRequestProperty("Referer", "https://share.weiyun.com/");
                conn.setRequestProperty("Accept", "text/html,application/xhtml+xml,*/*;q=0.8");
                if (conn.getResponseCode() == 200) {
                    InputStream in = conn.getInputStream();
                    String html = readAll(in);
                    in.close();
                    text = extractNotice(html);
                }
                conn.disconnect();
            } catch (Exception ignored) {
                // 拉取失败走兜底文案
            }
            noticeFetching = false;

            String result = text;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) {
                    return;
                }
                if (result != null && !result.isEmpty()) {
                    latestNotice = result;
                    noticeText.setText(result);
                } else if (latestNotice == null) {
                    noticeText.setText(DEFAULT_NOTICE);
                }
            });
        }).start();
    }

    /** 从微云分享页 HTML 里取出笔记正文，再用"取中间文本"解析 标签{内容} 字段。 */
    private String extractNotice(String html) {
        Matcher m = Pattern.compile(
                        "window\\.syncData\\s*=\\s*(\\{.*?\\})\\s*;",
                        Pattern.DOTALL)
                .matcher(html);
        if (!m.find()) {
            return null;
        }
        try {
            JSONObject data = new JSONObject(m.group(1));
            // 微云分享页的 syncData 里，note_list 嵌套在 shareInfo 里层
            JSONObject share = data.optJSONObject("shareInfo");
            JSONArray notes = (share != null ? share : data).optJSONArray("note_list");
            if (notes == null || notes.length() == 0) {
                return null;
            }
            JSONObject note = notes.getJSONObject(0);
            String content = note.optString("html_content", "");
            if (content.isEmpty()) {
                content = note.optString("note_title", "");
            }
            if (content.isEmpty() && share != null) {
                content = share.optString("share_name", "");
            }
            if (content.isEmpty()) {
                return null;
            }
            String plain = Html.fromHtml(content, Html.FROM_HTML_MODE_LEGACY)
                    .toString()
                    .trim();
            String result = parseFields(plain);
            return result.isEmpty() ? null : result;
        } catch (Exception e) {
            return null;
        }
    }

    /**
     * 取中间文本：逐行解析"标签{内容}"。
     * 标签（花括号前面的文本）保持不变，只提取花括号里的内容并原样重组；
     * 以后在微云笔记里加新字段（如 维护时间{...}）也会被自动带出来。
     */
    private String parseFields(String plain) {
        StringBuilder sb = new StringBuilder();
        Pattern fieldPattern = Pattern.compile("^([^\\{]*)\\{([^}]*)\\}\\s*$");
        for (String raw : plain.split("\n")) {
            String line = raw.trim();
            if (line.isEmpty()) {
                continue;
            }
            Matcher fm = fieldPattern.matcher(line);
            if (fm.find()) {
                String label = fm.group(1).trim();
                String value = fm.group(2).trim();
                sb.append(label).append("{").append(value).append("}\n");
            } else {
                sb.append(line).append("\n");
            }
        }
        return sb.toString().trim();
    }

    private static String readAll(InputStream in) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) != -1) {
            out.write(buf, 0, n);
        }
        return out.toString("UTF-8");
    }

    // ---------- 系统回调 ----------

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQUEST_FILE_CHOOSER) {
            if (filePathCallback != null) {
                Uri result = (data != null && resultCode == RESULT_OK) ? data.getData() : null;
                filePathCallback.onReceiveValue(result != null ? new Uri[]{result} : null);
                filePathCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        // 返回键优先回退网页历史，而不是直接退出 App
        if (keyCode == KeyEvent.KEYCODE_BACK
                && webView.getVisibility() == View.VISIBLE
                && webView.canGoBack()) {
            webView.goBack();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    protected void onDestroy() {
        if (filePathCallback != null) {
            filePathCallback.onReceiveValue(null);
            filePathCallback = null;
        }
        webView.destroy();
        super.onDestroy();
    }
}
