package com.liyang.community;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.webkit.CookieManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * 推送通知服务（轻量轮询）。
 *
 * 立洋社区 App 是 WebView 套壳，没有接入 FCM/厂商推送；这里采用前台服务 +
 * 定时轮询后端未读接口的方式，在收到新点赞/评论/粉丝/私信/系统通知时弹出系统通知，
 * 行为尽量贴近抖音/快手。通知开关由网页端"消息通知中心"设置，保存到 SharedPreferences
 * （与后端云端设置保持一致），并同步给本服务。
 *
 * 工作方式：
 * - 每 NOTIFY_POLL_MS（60s）请求一次 /notifications 与 /messages；
 * - 只推送"上次已通知之后新增"的通知（按通知 id / 会话未读基数去重）；
 * - 用户关闭某项开关后，对应类型不再弹通知。
 */
public class NotificationService extends Service {

    private static final String CHANNEL_MAIN = "ly_notify_main";
    private static final String CHANNEL_FOREGROUND = "ly_notify_service";

    public static final String PREF_NAME = "ly_notification_prefs";
    public static final String PREF_JSON = "prefs_json";

    private static final String LAST_SEEN_PREFIX = "last_seen_";
    private static final String DM_FP_KEY = "dm_fingerprint";

    private static final long NOTIFY_POLL_MS = 60_000L;
    private static final int SERVICE_ID = 2026;

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private Thread worker;
    private volatile boolean running;

    @Override
    public void onCreate() {
        super.onCreate();
        createChannels();
        startForeground(SERVICE_ID, buildServiceNotification());
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startWorker();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        if (worker != null) {
            worker.interrupt();
            worker = null;
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    /** 后台线程轮询，避免阻塞主线程（WebView 渲染需要主线程空闲）。 */
    private synchronized void startWorker() {
        if (running) return;
        running = true;
        worker = new Thread(() -> {
            while (running) {
                try {
                    pollOnce();
                } catch (Exception ignored) {
                }
                try {
                    Thread.sleep(NOTIFY_POLL_MS);
                } catch (InterruptedException ie) {
                    break;
                }
            }
        }, "ly-notify-worker");
        worker.setDaemon(false);
        worker.start();
    }

    // ---------- 权限与渠道 ----------

    private void createChannels() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm == null) return;
        NotificationChannel main = new NotificationChannel(
                CHANNEL_MAIN,
                "消息通知",
                NotificationManager.IMPORTANCE_HIGH);
        main.setDescription("点赞、评论、粉丝、私信、系统通知");
        nm.createNotificationChannel(main);
        NotificationChannel fg = new NotificationChannel(
                CHANNEL_FOREGROUND,
                "通知服务",
                NotificationManager.IMPORTANCE_LOW);
        fg.setDescription("用于在后台接收新消息提醒");
        fg.setShowBadge(false);
        nm.createNotificationChannel(fg);
    }

    private Notification buildServiceNotification() {
        Intent i = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(
                this, 0, i,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this, CHANNEL_FOREGROUND)
                .setContentTitle("立洋社区")
                .setContentText("通知服务运行中，有新消息会第一时间提醒你")
                .setSmallIcon(android.R.drawable.ic_popup_sync)
                .setContentIntent(pi)
                .setOngoing(true)
                .build();
    }

    // ---------- 偏好 ----------

    private SharedPreferences prefs() {
        return getSharedPreferences(PREF_NAME, MODE_PRIVATE);
    }

    /** 读取当前通知偏好（默认全开）。 */
    public static NotificationPrefs readPrefs(Context ctx) {
        SharedPreferences sp = ctx.getSharedPreferences(PREF_NAME, MODE_PRIVATE);
        String raw = sp.getString(PREF_JSON, null);
        NotificationPrefs p = new NotificationPrefs();
        if (raw == null) return p;
        try {
            JSONObject o = new JSONObject(raw);
            p.like = o.optBoolean("like", true);
            p.comment = o.optBoolean("comment", true);
            p.mention = o.optBoolean("mention", true);
            p.follow = o.optBoolean("follow", true);
            p.system = o.optBoolean("system", true);
            p.dm = o.optBoolean("dm", true);
        } catch (Exception ignored) {
            // 解析失败保持默认全开
        }
        return p;
    }

    /** 保存偏好（网页端保存云端设置后同步调用）。 */
    public static void savePrefs(Context ctx, String json) {
        ctx.getSharedPreferences(PREF_NAME, MODE_PRIVATE)
                .edit()
                .putString(PREF_JSON, json)
                .apply();
    }

    /** 记录某类已通知的最大通知 id。 */
    private long lastSeen(String type) {
        return prefs().getLong(LAST_SEEN_PREFIX + type, 0L);
    }

    private void setLastSeen(String type, long id) {
        prefs().edit().putLong(LAST_SEEN_PREFIX + type, id).apply();
    }

    // ---------- 轮询 ----------

    private void pollOnce() {
        try {
            String token = CookieManager.getInstance().getCookie(MainActivity.APP_URL);
            if (token == null || !token.contains("access_token")) {
                return; // 未登录，跳过
            }
            final NotificationPrefs p = readPrefs(this);
            pollNotifications(p);
            pollDm(p);
        } catch (Exception ignored) {
            // 网络抖动等静默忽略，下一轮重试
        }
    }

    /** 轮询 /notifications?page_size=20，按类型推送新增通知。 */
    private void pollNotifications(NotificationPrefs p) {
        JSONObject body = getJson(MainActivity.APP_URL + "/notifications?page_size=20");
        if (body == null) return;
        JSONArray items = body.optJSONObject("data")
                .optJSONArray("items");
        if (items == null) return;
        for (int i = items.length() - 1; i >= 0; i--) { // 最早的优先，保证顺序
            JSONObject item = items.optJSONObject(i);
            if (item == null) continue;
            long id = item.optLong("id");
            String type = item.optString("type", "system");
            boolean enabled = enabled(p, type);
            long seen = lastSeen(type);
            if (enabled && id > seen) {
                notifyItem(type, item.optString("title"), item.optString("content"));
            }
            if (id > seen) {
                setLastSeen(type, id);
            }
        }
    }

    /**
     * 轮询私信会话列表，检测"对方发来的新消息"。
     * 策略：保存每个会话最近一次看到的未读数；只有当某个会话的未读数
     * 比上次看到的更多时才弹通知（自己读消息/发消息不会误报）。
     */
    private void pollDm(NotificationPrefs p) {
        JSONObject body = getJson(MainActivity.APP_URL + "/messages");
        if (body == null) return;
        JSONObject dataObj = body.optJSONObject("data");
        if (dataObj == null) return;
        JSONArray list = dataObj.optJSONArray("items");
        if (list == null) {
            list = dataObj.optJSONArray("conversations");
        }
        if (list == null) return;

        JSONObject baseline = new JSONObject();
        try {
            String old = prefs().getString(DM_FP_KEY, "");
            if (!old.isEmpty()) {
                baseline = new JSONObject(old);
            }
        } catch (Exception ignored) {
            baseline = new JSONObject();
        }

        JSONObject next = new JSONObject();
        JSONObject best = null;
        long bestNewUnread = 0;
        long totalNewUnread = 0;
        for (int i = 0; i < list.length(); i++) {
            JSONObject c = list.optJSONObject(i);
            if (c == null) continue;
            JSONObject user = c.optJSONObject("user");
            long uid = user != null ? user.optLong("id") : c.optLong("user_id");
            if (uid <= 0) continue;
            long unread = c.optLong("unread_count");
            long seen = baseline.optLong(String.valueOf(uid), -1L);
            long newUnread = seen >= 0 && unread > seen ? unread - seen : 0;
            if (newUnread > 0) {
                totalNewUnread += newUnread;
                if (newUnread > bestNewUnread) {
                    bestNewUnread = newUnread;
                    best = c;
                }
            }
            try {
                next.put(String.valueOf(uid), unread);
            } catch (Exception ignored) {
            }
        }

        if (p.dm && totalNewUnread > 0) {
            if (totalNewUnread > 1 && best == null) {
                notifyItem("dm", "立洋社区", "你有 " + totalNewUnread + " 条新私信，点击查看");
            } else if (best != null) {
                JSONObject user = best.optJSONObject("user");
                String name = user != null ? user.optString("nickname", "新消息") : "新消息";
                String content = best.optString("last_message", "点击查看");
                if ("image".equals(best.optString("msg_type")) || "image".equals(best.optString("last_msg_type")) || isImageLike(content)) {
                    content = "[图片]";
                } else if ("voice".equals(best.optString("msg_type")) || "voice".equals(best.optString("last_msg_type"))) {
                    content = "[语音]";
                }
                if (bestNewUnread > 1) {
                    content = "你有 " + bestNewUnread + " 条新私信：" + content;
                }
                notifyItem("dm", name + " 发来私信", content);
            }
        }

        if (next.length() > 0) {
            prefs().edit().putString(DM_FP_KEY, next.toString()).apply();
        }
    }

    private boolean isImageLike(String s) {
        return s != null && (s.startsWith("/uploads/") || s.startsWith("/images/")
                || s.startsWith("http://") || s.startsWith("https://"));
    }

    private boolean enabled(NotificationPrefs p, String type) {
        switch (type) {
            case "like":
                return p.like;
            case "comment":
                return p.comment;
            case "mention":
                return p.mention;
            case "follow":
                return p.follow;
            case "system":
            case "announcement":
            case "interaction":
            case "topic":
            case "vote_end":
                return p.system;
            default:
                return true;
        }
    }

    private void notifyItem(String type, String title, String content) {
        mainHandler.post(() -> {
            Intent i = new Intent(this, MainActivity.class);
            i.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
            PendingIntent pi = PendingIntent.getActivity(
                    this,
                    (int) (System.currentTimeMillis() % 100000),
                    i,
                    PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
            Notification.Builder b = new Notification.Builder(this, CHANNEL_MAIN)
                    .setSmallIcon(android.R.drawable.ic_popup_sync)
                    .setContentTitle(title != null && !title.isEmpty() ? title : "立洋社区")
                    .setContentText(content != null && !content.isEmpty() ? content : "你有新的消息")
                    .setContentIntent(pi)
                    .setAutoCancel(true)
                    .setPriority(Notification.PRIORITY_HIGH);
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                nm.notify(type.hashCode(), b.build());
            }
        });
    }

    private JSONObject getJson(String urlStr) {
        try {
            URL url = new URL(urlStr);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(10000);
            conn.setRequestProperty("Cookie", CookieManager.getInstance().getCookie(MainActivity.APP_URL));
            conn.setRequestProperty("Accept", "application/json");
            int code = conn.getResponseCode();
            if (code != 200) {
                conn.disconnect();
                return null;
            }
            StringBuilder sb = new StringBuilder();
            try (BufferedReader br = new BufferedReader(
                    new InputStreamReader(conn.getInputStream(), "UTF-8"))) {
                String line;
                while ((line = br.readLine()) != null) {
                    sb.append(line);
                }
            }
            conn.disconnect();
            return new JSONObject(sb.toString());
        } catch (Exception e) {
            return null;
        }
    }

    /** 通知偏好数据类。 */
    public static class NotificationPrefs {
        public boolean like = true;
        public boolean comment = true;
        public boolean mention = true;
        public boolean follow = true;
        public boolean system = true;
        public boolean dm = true;

        public JSONObject toJson() {
            JSONObject o = new JSONObject();
            try {
                o.put("like", like);
                o.put("comment", comment);
                o.put("mention", mention);
                o.put("follow", follow);
                o.put("system", system);
                o.put("dm", dm);
            } catch (Exception ignored) {
            }
            return o;
        }
    }

}
