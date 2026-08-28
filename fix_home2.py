# -*- coding: utf-8 -*-
import pathlib

p = pathlib.Path(r"d:/Users/Downloads/同伴圈/frontend/src/views/HomeView.vue")
s = p.read_text(encoding="utf-8")

# === 1. Add helper functions after gatheringCountdown ===
old_gath_funcs = """function gatheringCountdown(start: string | null): string {
  if (!start) return '即将开始'
  const t = new Date(start).getTime()
  if (Number.isNaN(t)) return '即将开始'
  const diff = t - Date.now()
  if (diff <= 0) return '进行中'
  const h = Math.floor(diff / 3600000)
  if (h >= 24) return `${Math.floor(h / 24)}天后开始`
  if (h >= 1) return `${h}小时后开始`
  const m = Math.floor((diff % 3600000) / 60000)
  return `${Math.max(1, m)}分钟后开始`
}"""

new_gath_funcs = """function gatheringCountdown(start: string | null): string {
  if (!start) return '即将开始'
  const t = new Date(start).getTime()
  if (Number.isNaN(t)) return '即将开始'
  const diff = t - Date.now()
  if (diff <= 0) return '进行中'
  const h = Math.floor(diff / 3600000)
  if (h >= 24) return `${Math.floor(h / 24)}天后开始`
  if (h >= 1) return `${h}小时后开始`
  const m = Math.floor((diff % 3600000) / 60000)
  return `${Math.max(1, m)}分钟后开始`
}

// === 首页房间卡片辅助函数（图1样式） ===
function categoryEmoji(cat: string | null): string {
  if (!cat) return '🎪'
  if (cat.includes('游戏')) return '🎮'
  if (cat.includes('现实') || cat.includes('线下')) return '📍'
  if (cat.includes('聊天') || cat.includes('扩列')) return '💬'
  if (cat.includes('搞笑')) return '⭐'
  if (cat.includes('学习')) return '📚'
  if (cat.includes('美食') || cat.includes('吃')) return '🍜'
  if (cat.includes('运动')) return '⚽'
  if (cat.includes('音乐')) return '🎵'
  if (cat.includes('电影')) return '🎬'
  return '🎪'
}

function categoryDisplayName(cat: string | null): string {
  if (!cat) return '推荐'
  return cat
}

function roomSubtitle(g: Gathering): string {
  // 优先显示描述（主题/标语），截断
  if (g.description && g.description.trim()) {
    const d = g.description.trim().replace(/\\n/g, ' ').replace(/\\s+/g, ' ')
    return d.length > 20 ? d.slice(0, 20) + '…' : d
  }
  // 否则显示主持人+时间
  const host = g.host?.nickname || '匿名'
  const timeAgo = g.start_time ? gatheringCountdown(g.start_time) : '即将开始'
  return `${host.slice(0, 6)} · ${timeAgo}`
}

function roomHostLabel(g: Gathering): string {
  // 房主角标文字
  const cat = g.category || ''
  if (cat.includes('搞笑')) return '搞笑房主'
  if (cat.includes('游戏')) return '游戏房主'
  if (cat.includes('聊天') || cat.includes('扩列')) return '聊天房主'
  return cat ? cat.slice(0, 4) + '房主' : '房主'
}

function shouldShowHostBadge(g: Gathering): boolean {
  // 显示房主角标：自己是房主 或 房间人数>=3（热门房主）
  if (g.is_host) return true
  if (g.joined_people >= 3) return true
  return false
}

function shouldShowHotBadge(g: Gathering): boolean {
  return g.joined_people >= 5
}

function avatarInitial(nickname: string | null | undefined): string {
  if (!nickname) return '?'
  return nickname.slice(0, 1).toUpperCase()
}

function avatarColorClass(id: number | null | undefined): string {
  return `av-${((id || 0) % 5) + 1}`
}

function onCardMore(e: Event, g: Gathering) {
  e.stopPropagation()
  // TODO: 显示更多操作菜单
  toast.success('更多操作')
}"""

s = s.replace(old_gath_funcs, new_gath_funcs)

# === 2. Replace the gatherings card template ===
old_template = """        <!-- ===== 为你推荐 / 游戏组局 / 现实组局：组局卡片（不包含广场帖子） ===== -->
        <template v-else>
          <div v-if="gatherings.length" :class="{ 'swr-updated': fadeActive }" class="feed feed--gatherings">
            <article
              v-for="g in gatherings"
              :key="'g-'+g.id"
              class="card card--image card--gathering"
              @click="openGathering(g)"
            >
              <div class="gathering-cover">
                <img
                  v-if="gatheringCover(g)"
                  class="card-img"
                  :src="gatheringCover(g)"
                  :alt="g.title"
                  loading="lazy"
                />
                <div v-else class="gathering-cover--ph">
                  <Icon name="calendar" :size="46" color="#ffffff" />
                </div>
                <span class="gathering-tag">{{ g.category || '推荐组局' }}</span>
                <span class="gathering-type" :class="g.type === 'online' ? 'is-online' : 'is-offline'">
                  {{ g.type === 'online' ? '线上' : '线下' }}
                </span>
              </div>
              <div class="card-body">
                <h3 class="card-title gathering-title">{{ g.title }}</h3>
                <div class="gathering-meta">
                  <span class="gathering-meta__item">
                    <Icon name="clock" :size="13" /> {{ gatheringCountdown(g.start_time) }}
                  </span>
                  <span v-if="g.location" class="gathering-meta__item">
                    <Icon name="map-pin" :size="13" /> {{ g.location }}
                  </span>
                </div>
                <div class="gathering-foot">
                  <div class="gathering-host">
                    <img
                      v-if="g.host?.avatar"
                      class="avatar avatar-xs avatar-img"
                      :src="g.host.avatar"
                      :alt="g.host.nickname"
                    />
                    <span v-else class="avatar avatar-xs" :class="`av-${(g.host?.id || 0) % 5 + 1}`">
                      {{ (g.host?.nickname || '组').slice(0,1) }}
                    </span>
                    <span class="gathering-host__name">{{ g.host?.nickname || '发起人' }}</span>
                  </div>
                  <div class="gathering-people">
                    <Icon name="users" :size="13" />
                    <span>{{ g.joined_people }}/{{ g.max_people }}</span>
                  </div>
                </div>
              </div>
            </article>
          </div>

          <div v-else-if="gatheringsError" class="feed-error">
            <p class="feed-error-text">加载失败，请检查网络后重试</p>
            <button class="feed-error-btn" type="button" @click="retryFeed">重新加载</button>
          </div>
          <EmptyState v-else icon="calendar" text="暂无招募中组局，稍后再来看看吧～" />
        </template>"""

new_template = """        <!-- ===== 所有 Tab：组局/房间卡片（图1样式，单列圆角卡片） ===== -->
        <template v-else>
          <div v-if="gatherings.length" :class="{ 'swr-updated': fadeActive }" class="room-feed">
            <article
              v-for="g in gatherings"
              :key="'g-'+g.id"
              class="room-card"
              @click="openGathering(g)"
            >
              <!-- 顶部：分类标签 + 房主角标 + 更多按钮 -->
              <div class="room-card__top">
                <div class="room-card__tags">
                  <span class="room-tag room-tag--category">
                    <span class="room-tag__emoji">{{ categoryEmoji(g.category) }}</span>
                    {{ categoryDisplayName(g.category) }}
                  </span>
                  <span v-if="shouldShowHostBadge(g)" class="room-tag room-tag--host">
                    <span class="room-tag__emoji">🏠</span>
                    {{ roomHostLabel(g) }}
                  </span>
                  <span v-if="shouldShowHotBadge(g) && !shouldShowHostBadge(g)" class="room-tag room-tag--hot">
                    <span class="room-tag__emoji">🔥</span>
                    热门
                  </span>
                </div>
                <button class="room-card__more" type="button" @click="onCardMore($event, g)" aria-label="更多">
                  <Icon name="more-horizontal" :size="20" />
                </button>
              </div>

              <!-- 中部：头像 + 房间名 + 副标题 -->
              <div class="room-card__body">
                <div class="room-card__avatar-wrap">
                  <img
                    v-if="g.host?.avatar"
                    class="room-card__avatar"
                    :src="g.host.avatar"
                    :alt="g.host.nickname"
                    loading="lazy"
                  />
                  <span v-else class="room-card__avatar room-card__avatar--ph" :class="avatarColorClass(g.host?.id)">
                    {{ avatarInitial(g.host?.nickname) }}
                  </span>
                  <!-- 头像右下角小标记（女性符号/在线标记） -->
                  <span class="room-card__avatar-badge" aria-hidden="true">
                    {{ g.type === 'online' ? '🎤' : '📍' }}
                  </span>
                </div>
                <div class="room-card__info">
                  <h3 class="room-card__title">{{ g.title }}</h3>
                  <p class="room-card__subtitle">{{ roomSubtitle(g) }}</p>
                  <div v-if="g.location" class="room-card__location">
                    <Icon name="map-pin" :size="12" />
                    <span>{{ g.location }}</span>
                  </div>
                </div>
              </div>

              <!-- 右下角：组局人数信息 -->
              <div class="room-card__foot">
                <span class="room-card__stat">
                  <Icon name="mic" :size="16" />
                  <span>{{ g.joined_people }}</span>
                </span>
                <span class="room-card__stat">
                  <Icon name="users" :size="16" />
                  <span>{{ g.joined_people }}/{{ g.max_people }}</span>
                </span>
              </div>
            </article>
          </div>

          <div v-else-if="gatheringsError" class="feed-error">
            <p class="feed-error-text">加载失败，请检查网络后重试</p>
            <button class="feed-error-btn" type="button" @click="retryFeed">重新加载</button>
          </div>
          <EmptyState v-else icon="calendar" text="暂无招募中组局，去发布一个吧～" />
        </template>"""

s = s.replace(old_template, new_template)

# === 3. Replace the old gathering CSS with new room card CSS ===
# Find and replace the old gathering card styles
old_css_start = "/* ===== 首页组局卡片（为你推荐/游戏组局/现实组局 Tab） ===== */"
old_css_end = "@media (min-width: 769px) {\n  .feed--gatherings { column-count: 2; column-gap: 20px; }\n  .gathering-cover { height: 230px; }\n  .gathering-title { font-size: 16px; }\n}"

# Find the old CSS block
css_start_idx = s.find(old_css_start)
if css_start_idx == -1:
    # Try alternate comment
    old_css_start = "/* ===== 首页组局卡片"
    css_start_idx = s.find(old_css_start)

if css_start_idx != -1:
    # Find the end of this CSS block - look for the next /* comment or media query end
    # The old block ends with the @media (min-width: 769px) block for gatherings
    end_marker = ".gathering-people :deep(svg) { width: 13px; height: 13px; }\n.avatar.avatar-xs {"
    end_idx = s.find(end_marker, css_start_idx)
    if end_idx != -1:
        # Find the end of the avatar-xs rule and the following @media block
        # Let's find a safe end point - the "/* 纯文字卡" comment
        next_section = "/* 纯文字卡"
        next_section_idx = s.find(next_section, css_start_idx)
        if next_section_idx != -1:
            old_css_block = s[css_start_idx:next_section_idx]
            new_css_block = """/* ===== 首页房间卡片（图1样式：单列圆角卡片） ===== */
.room-feed {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0 0 8px;
}

.room-card {
  position: relative;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-radius: 20px;
  padding: 16px 18px 14px;
  cursor: pointer;
  text-align: left;
  border: none;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  transition: transform 150ms ease, box-shadow 150ms ease;
  overflow: hidden;
}
.room-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  transform: translateY(-1px);
}
.room-card:active {
  transform: scale(0.985);
}

/* 顶部：标签 + 更多 */
.room-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 14px;
}
.room-card__tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}
.room-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 600;
  line-height: 1.4;
  white-space: nowrap;
}
.room-tag__emoji {
  font-size: 14px;
  line-height: 1;
}
.room-tag--category {
  background: #f5f5f7;
  color: #333;
}
.room-tag--host {
  background: linear-gradient(135deg, #e0f7fa, #b2ebf2);
  color: #00838f;
}
.room-tag--hot {
  background: linear-gradient(135deg, #fff3e0, #ffe0b2);
  color: #e65100;
}

.room-card__more {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: transparent;
  border: none;
  color: #bbb;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 150ms ease, color 150ms ease;
}
.room-card__more:hover {
  background: #f5f5f7;
  color: #666;
}

/* 中部：头像 + 信息 */
.room-card__body {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 10px;
}
.room-card__avatar-wrap {
  position: relative;
  flex-shrink: 0;
}
.room-card__avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  object-fit: cover;
  display: inline-block;
  background: #e5e5ea;
  border: 2px solid #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.room-card__avatar--ph {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 700;
  color: #fff;
}
.room-card__avatar-badge {
  position: absolute;
  right: -2px;
  bottom: -2px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #ff4081;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  border: 2px solid #fff;
  line-height: 1;
}

.room-card__info {
  flex: 1;
  min-width: 0;
  padding-top: 2px;
}
.room-card__title {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 700;
  color: #1a1a1a;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.room-card__subtitle {
  margin: 0;
  font-size: 13.5px;
  color: #999;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.room-card__location {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-top: 4px;
  font-size: 12px;
  color: #0a6cff;
}
.room-card__location :deep(svg) {
  width: 12px;
  height: 12px;
}

/* 底部：右下角统计 */
.room-card__foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  margin-top: auto;
  padding-top: 4px;
}
.room-card__stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  color: #888;
  font-weight: 500;
}
.room-card__stat :deep(svg) {
  width: 18px;
  height: 18px;
  color: #999;
}

/* Mobile adjustments */
@media (max-width: 768px) {
  .room-feed {
    gap: 10px;
  }
  .room-card {
    padding: 14px 14px 12px;
    border-radius: 18px;
  }
  .room-card__avatar {
    width: 50px;
    height: 50px;
  }
  .room-card__avatar--ph {
    font-size: 20px;
  }
  .room-card__title {
    font-size: 18px;
  }
  .room-card__subtitle {
    font-size: 13px;
  }
  .room-tag {
    font-size: 12px;
    padding: 2px 8px;
  }
}

"""
            s = s[:css_start_idx] + new_css_block + s[next_section_idx:]
            print("OK: Template and CSS replaced")
        else:
            print("ERROR: Could not find next section marker")
    else:
        print("ERROR: Could not find end marker")
else:
    print("ERROR: Could not find old CSS start")

p.write_text(s, encoding="utf-8")
print("DONE: HomeView.vue updated")
