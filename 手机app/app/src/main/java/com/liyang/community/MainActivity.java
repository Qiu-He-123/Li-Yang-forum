package com.liyang.community;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.NotificationManager;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.Build;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.Html;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import android.window.OnBackInvokedCallback;
import android.window.OnBackInvokedDispatcher;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Arrays;
import java.util.Locale;
import java.util.Set;
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
    private static final int REQUEST_POST_NOTIFICATIONS = 1002;
    /** 内核主版本号低于该值就提示更新（Chromium 100 ≈ 2022 年的内核） */
    private static final int MIN_WEBVIEW_MAJOR = 100;
    /** 要打开的网页地址（改这里即可，不用 strings.xml） */
    public static final String APP_URL = "https://al.u3593529.nyat.app:32449";
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
    private View splashPanel;
    private TextView noticeText;
    private String latestNotice;
    private boolean noticeFetching;
    private boolean splashHidden;
    private long splashShownAt;
    private boolean exitRequested;
    private OnBackInvokedCallback backCallback;
    private ValueCallback<Uri[]> filePathCallback;
    /** 启动页至少展示的时间，避免一闪而过 */
    private static final long MIN_SPLASH_MS = 1200;
    /** 定期把 Cookie 落盘，防止进程被杀导致登录态丢失 */
    private static final long COOKIE_FLUSH_INTERVAL_MS = 30_000;
    /** 文件选择器结果复制到缓存目录时的临时目录名 */
    private static final String UPLOAD_CACHE_DIR = "upload";
    /** 上传缓存目录最大保留量，超过时按最旧优先清理（防止缓存目录被塞满） */
    private static final long UPLOAD_CACHE_MAX_BYTES = 200L * 1024 * 1024;

    private final Handler cookieFlushHandler = new Handler(Looper.getMainLooper());
    private final Runnable cookieFlushTask = new Runnable() {
        @Override
        public void run() {
            CookieManager.getInstance().flush();
            cookieFlushHandler.postDelayed(this, COOKIE_FLUSH_INTERVAL_MS);
        }
    };

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
        applySystemBarPadding();

        webView = findViewById(R.id.webView);
        progressBar = findViewById(R.id.progressBar);
        offlinePanel = findViewById(R.id.offlinePanel);
        kernelPanel = findViewById(R.id.kernelPanel);
        splashPanel = findViewById(R.id.splashPanel);
        noticeText = findViewById(R.id.noticeText);
        splashShownAt = SystemClock.uptimeMillis();

        setupWebView();
        setupPanels();
        setupBackHandler();
        cookieFlushHandler.postDelayed(cookieFlushTask, COOKIE_FLUSH_INTERVAL_MS);

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
          // 文件选择必须允许访问内容 URI / 文件，否则网页上传图片会失败
          settings.setAllowFileAccess(true);
          settings.setAllowContentAccess(true);
          // 自定义 UA 标记：前端可用 navigator.userAgent.includes('LYCommunityApp') 区分 App 和网页版
        settings.setUserAgentString(
                WebSettings.getDefaultUserAgent(this) + " LYCommunityApp/1.0");

        CookieManager.getInstance().setAcceptCookie(true);
        webView.addJavascriptInterface(new LyJsBridge(), "LYCommunityApp");
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
                hideSplashWhenReady();
                syncNotificationService();
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
                try {
                    // 直接用 createIntent() 返回的 ACTION_GET_CONTENT 启动。
                    // 不要再包一层 Intent.createChooser：系统选择器本身就有应用列表，
                    // 且部分机型经过 chooser 转发后会丢 ClipData / 结果，导致网页端毫无反应。
                    Intent intent = fileChooserParams.createIntent();
                    intent.addCategory(Intent.CATEGORY_OPENABLE);
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP
                            && fileChooserParams.getMode()
                                    == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE) {
                        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                    }
                    // 显式带上网页声明的可接受类型，避免部分机型只能选到非图片文件
                    String[] acceptTypes = fileChooserParams.getAcceptTypes();
                    if (acceptTypes != null && acceptTypes.length > 0) {
                        intent.putExtra(Intent.EXTRA_MIME_TYPES, acceptTypes);
                    }
                    startActivityForResult(intent, REQUEST_FILE_CHOOSER);
                } catch (Exception e) {
                    MainActivity.this.filePathCallback.onReceiveValue(null);
                    MainActivity.this.filePathCallback = null;
                    return false;
                }
                return true;
            }
        });
    }

    /**
     * 返回键处理：优先回退网页历史（返回上一级），而不是直接退出整个 App。
     * Android 13+ 的返回手势走 OnBackInvokedCallback，老版本走 onKeyDown/onBackPressed，
     * 这里三条路都接上，保证各种手机上行为一致。
     */
    private void setupBackHandler() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            backCallback = this::handleBack;
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                    backCallback);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        syncNotificationService();
    }

    private void handleBack() {
        // 维护页 / 内核提示页没有网页历史，返回 = 退出
        if (offlinePanel.getVisibility() == View.VISIBLE
                || kernelPanel.getVisibility() == View.VISIBLE) {
            exitApp();
            return;
        }
        // 网页能回退（帖子详情 → 首页等）就走网页历史
        if (webView.canGoBack()) {
            webView.goBack();
            return;
        }
        // 已经在最顶层：2 秒内连按两次才退出，防止误触直接关掉 App
        if (exitRequested) {
            finishAndRemoveTask();
        } else {
            exitRequested = true;
            Toast.makeText(this, "再按一次返回键退出", Toast.LENGTH_SHORT).show();
            webView.postDelayed(() -> exitRequested = false, 2000);
        }
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

    /**
     * 状态栏/刘海安全区适配（只在 App 里做，不动网页）。
     * Android 15/16 会强制 edge-to-edge，网页内容会顶到屏幕最上方、
     * 被摄像头/状态栏遮挡；这里检测到内容真的画到状态栏下面时，
     * 给根布局补上状态栏高度的顶部内边距，把整个页面往下推。
     * 老版本安卓系统已自动避让状态栏，检测到不需要时不动，避免重复加高。
     */
    private void applySystemBarPadding() {
        View root = findViewById(R.id.rootLayout);
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int topInset = 0;
            int imeBottom = 0;
            int bottomInset = 0;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                topInset = insets.getInsets(WindowInsets.Type.statusBars()).top;
                // 底部导航栏（三键返回键 / 手势条）：和三键手机上的微信一样，
                // 内容要抬到导航栏上方，不能把按钮顶到返回键底下。
                bottomInset = insets.getInsets(WindowInsets.Type.navigationBars()).bottom;
                // 软键盘：Android 15/16 强制全屏时 adjustResize 可能失效，
                // 这里手动给底部补键盘高度，输入框才能浮到输入法上方（类似微信）
                if (insets.isVisible(WindowInsets.Type.ime())) {
                    imeBottom = insets.getInsets(WindowInsets.Type.ime()).bottom;
                }
            } else {
                topInset = insets.getSystemWindowInsetTop();
                bottomInset = insets.getSystemWindowInsetBottom();
            }
            int top = topInset;
            int bottom = Math.max(imeBottom, bottomInset);
            // 等布局完成后再判断，避免第一次回调时拿不到真实位置
            v.post(() -> {
                if (isFinishing() || isDestroyed()) {
                    return;
                }
                int[] loc = new int[2];
                v.getLocationOnScreen(loc);
                // 内容顶到了状态栏下面（edge-to-edge）才补顶部内边距
                int padTop = (top > 0 && loc[1] < top) ? top : 0;
                // 底部同样：只有内容真的画到了导航栏区域（根布局底边贴近屏幕底边）
                // 才补导航栏高度，避免系统已自动避让时重复加高出现空白。
                int padBottom = 0;
                if (bottom > 0) {
                    android.util.DisplayMetrics dm = new android.util.DisplayMetrics();
                    getWindowManager().getDefaultDisplay().getRealMetrics(dm);
                    int rootBottom = loc[1] + v.getHeight();
                    if (rootBottom >= dm.heightPixels - bottom + 1) {
                        padBottom = bottom;
                    }
                }
                v.setPadding(0, padTop, 0, padBottom);
            });
            return insets;
        });
    }

    // ---------- 原生桥接（网页端调用） ----------

    /**
     * 暴露给网页的桥：window.LYCommunityApp
     * - setNotificationPrefs(json): 保存通知偏好，并控制推送服务启停
     * - getNotificationPrefs(): 读取当前通知偏好
     * - requestNotificationPermission(): 请求系统通知权限（Android 13+）
     */
    private class LyJsBridge {
        @JavascriptInterface
        public void setNotificationPrefs(String json) {
            NotificationService.savePrefs(MainActivity.this, json);
            syncNotificationService();
        }

        @JavascriptInterface
        public String getNotificationPrefs() {
            return NotificationService.readPrefs(MainActivity.this).toJson().toString();
        }

        @JavascriptInterface
        public void requestNotificationPermission() {
            ensureNotificationPermission();
        }
    }

    /** Android 13+ 需要动态申请 POST_NOTIFICATIONS 权限。 */
    private boolean hasNotificationPermission() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU
                || checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
                        == PackageManager.PERMISSION_GRANTED;
    }

    private void ensureNotificationPermission() {
        if (hasNotificationPermission()) return;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            requestPermissions(
                    new String[]{android.Manifest.permission.POST_NOTIFICATIONS},
                    REQUEST_POST_NOTIFICATIONS);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_POST_NOTIFICATIONS
                && grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            syncNotificationService();
        }
    }

    /** 根据通知偏好启停后台推送服务：有任意分类开启 + 系统权限授予时才启动。 */
    private void syncNotificationService() {
        NotificationService.NotificationPrefs p =
                NotificationService.readPrefs(this);
        boolean anyEnabled = p.like || p.comment || p.mention || p.follow || p.system || p.dm;
        if (!anyEnabled || !hasNotificationPermission()) {
            stopService(new Intent(this, NotificationService.class));
            return;
        }
        String cookie = CookieManager.getInstance().getCookie(APP_URL);
        if (cookie == null || !cookie.contains("access_token")) {
            stopService(new Intent(this, NotificationService.class));
            return;
        }
        startService(new Intent(this, NotificationService.class));
    }

    // ---------- 文件选择器结果处理 ----------


    /**
     * 把系统文件选择器返回的 content:// URI 复制到应用私有缓存目录，
     * 再以 file:// URI 交给网页。部分相册/文件 App 返回的 content:// URI
     * 只对"选择器"授权、对 WebView 不可读，网页拿到后 File 对象为空、
     * change 事件不触发 → 表现为"选了图片但页面毫无反应"。
     * 复制到自己的缓存目录后 WebView 一定能读，这是官方文档推荐的稳妥做法。
     */
    private Uri[] copyResultsToCache(Uri[] uris) {
        if (uris == null || uris.length == 0) {
            return uris;
        }
        try {
            File dir = new File(getCacheDir(), UPLOAD_CACHE_DIR);
            if (!dir.exists()) {
                //noinspection ResultOfMethodCallIgnored
                dir.mkdirs();
            }
            cleanupUploadCache(dir);
            Uri[] out = new Uri[uris.length];
            for (int i = 0; i < uris.length; i++) {
                out[i] = copyUriToCache(uris[i], dir, i);
            }
            return out;
        } catch (Exception e) {
            // 复制失败就退回原 URI，让网页端自己报错
            return uris;
        }
    }

    private Uri copyUriToCache(Uri uri, File dir, int index) {
        if (uri == null) {
            return null;
        }
        String scheme = uri.getScheme();
        // file:// 和 http(s):// 本来就能读，不用复制
        if ("file".equals(scheme) || "http".equals(scheme) || "https".equals(scheme)) {
            return uri;
        }
        File dst = new File(dir, System.currentTimeMillis() + "_" + index + guessImageExtension(uri));
        try (InputStream in = getContentResolver().openInputStream(uri);
             FileOutputStream out = new FileOutputStream(dst)) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) != -1) {
                out.write(buf, 0, n);
            }
            return Uri.fromFile(dst);
        } catch (Exception e) {
            return uri;
        }
    }

    private String guessImageExtension(Uri uri) {
        String mime = null;
        try {
            mime = getContentResolver().getType(uri);
        } catch (Exception ignored) {
            // 某些 picker 的 URI 拿不到 MIME，走兜底
        }
        if (mime == null && uri.getLastPathSegment() != null) {
            mime = uri.getLastPathSegment();
        }
        if (mime != null) {
            String lower = mime.toLowerCase(Locale.US);
            if (lower.contains("jpeg") || lower.contains("jpg")) return ".jpg";
            if (lower.contains("png")) return ".png";
            if (lower.contains("gif")) return ".gif";
            if (lower.contains("webp")) return ".webp";
            if (lower.contains("heic")) return ".heic";
            if (lower.contains("bmp")) return ".bmp";
        }
        return ".jpg";
    }

    /** 缓存目录超过上限时，按最旧优先删除，避免上传大图把缓存塞满 */
    private void cleanupUploadCache(File dir) {
        File[] files = dir.listFiles();
        if (files == null || files.length == 0) {
            return;
        }
        long total = 0;
        for (File f : files) {
            total += f.length();
        }
        if (total <= UPLOAD_CACHE_MAX_BYTES) {
            return;
        }
        Arrays.sort(files, (a, b) -> Long.compare(a.lastModified(), b.lastModified()));
        for (File f : files) {
            if (total <= UPLOAD_CACHE_MAX_BYTES) {
                break;
            }
            total -= f.length();
            //noinspection ResultOfMethodCallIgnored
            f.delete();
        }
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
        hideSplashNow();
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
        hideSplashNow();
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

    // ---------- 启动页 ----------

    private void hideSplashWhenReady() {
        long wait = Math.max(0, MIN_SPLASH_MS - (SystemClock.uptimeMillis() - splashShownAt));
        splashPanel.postDelayed(this::hideSplash, wait);
    }

    private void hideSplash() {
        if (splashHidden) {
            return;
        }
        splashHidden = true;
        splashPanel.animate()
                .alpha(0f)
                .setDuration(350)
                .withEndAction(() -> splashPanel.setVisibility(View.GONE))
                .start();
    }

    /** 出错/内核提示等场景直接移除启动页，不淡出 */
    private void hideSplashNow() {
        if (splashHidden) {
            return;
        }
        splashHidden = true;
        splashPanel.setVisibility(View.GONE);
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
                // parseResult 兼容单选/多选/取消，避免部分机型 getData() 为空；
                // 再把 content:// 复制成 file://，保证 WebView 一定能读
                Uri[] results =
                        WebChromeClient.FileChooserParams.parseResult(resultCode, data);
                filePathCallback.onReceiveValue(copyResultsToCache(results));
                filePathCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            handleBack();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    public void onBackPressed() {
        handleBack();
    }

    @Override
    protected void onPause() {
        super.onPause();
        // 退到后台/即将被杀前先把 Cookie 写入磁盘，保证下次打开还是登录状态
        CookieManager.getInstance().flush();
    }

    @Override
    protected void onStop() {
        super.onStop();
        CookieManager.getInstance().flush();
    }

    @Override
    protected void onDestroy() {
        cookieFlushHandler.removeCallbacks(cookieFlushTask);
        // 必须先落盘再销毁 WebView，否则登录 Cookie 可能丢失
        CookieManager.getInstance().flush();
        if (backCallback != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback(backCallback);
            backCallback = null;
        }
        if (filePathCallback != null) {
            filePathCallback.onReceiveValue(null);
            filePathCallback = null;
        }
        webView.destroy();
        super.onDestroy();
    }
}
