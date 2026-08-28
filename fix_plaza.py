# -*- coding: utf-8 -*-
import pathlib

p = pathlib.Path(r"d:/Users/Downloads/同伴圈/frontend/src/views/CircleDiscover.vue")
s = p.read_text(encoding="utf-8")

# === 1. Replace the post card template section ===
old_card_start = """            <!-- 顶部：头像 / 昵称-推荐时间 / 关注 / 更多  (严格按用户截图1) -->
            <div class="post-card__head">
              <button
                class="post-card__author"
                type="button"
                @click="(e) => openAuthorHome(e, post)"
              >
                <img
                  v-if="!post.is_anonymous && post.author_avatar_url"
                  class="post-card__avatar"
                  :src="post.author_avatar_url"
                  :alt="post.author"
                  loading="lazy"
                />
                <span
                  v-else
                  class="post-card__avatar post-card__avatar--ph"
                  :class="`av-${(post.author_id || 0) % 5 + 1}`"
                >{{ post.is_anonymous ? '匿' : (post.author || 'U').slice(0,1) }}</span>
                <div class="post-card__author-info">
                  <div class="post-card__name-row">
                    <span class="post-card__name">{{ post.is_anonymous ? '匿名同学' : post.author }}</span>
                    <span v-if="post.author_badge?.name" class="post-card__badge">{{ post.author_badge.name }}</span>
                  </div>
                  <div class="post-card__sub">
                    <span>{{ formatRelativeTime(post.created_at) }}推荐</span>
                    <span v-if="post.topic_name" class="post-card__sub-dot"></span>
                    <span v-if="post.topic_name" class="post-card__sub-topic">#{{ post.topic_name }}</span>
                  </div>
                </div>
              </button>

              <div class="post-card__actions-top">
                <button
                  v-if="!post.is_anonymous && post.author_id && post.author_id !== session.userId"
                  class="post-card__follow"
                  :class="{ 'is-following': isFollowingAuthor(post) }"
                  type="button"
                  @click="(e) => onToggleFollowPostAuthor(e, post)"
                >
                  {{ isFollowingAuthor(post) ? '关注' : '关注' }}
                  <!-- 朋友圈风格：始终显示「关注」(蓝色按钮)，已关注就灰色文字表示已关注 -->
                  <template v-if="isFollowingAuthor(post)">&nbsp;</template>
                </button>
                <button class="post-card__more" type="button" aria-label="更多">
                  <Icon name="more-horizontal" :size="20" />
                </button>
              </div>
            </div>

            <!-- 正文文字（朋友圈风格：整段显示，不截断） -->
            <p v-if="post.content" class="post-card__text">{{ post.content }}</p>

            <!-- 分类/审核标签（和正文之间小间距） -->
            <div v-if="post.ai_status || post.is_public === false" class="post-card__badges">
              <span v-if="post.is_public === false" class="post-card__tag post-card__tag--warn">
                <Icon name="lock" :size="11" /> 已私密
              </span>
              <AiStatusBadge
                v-if="post.ai_status"
                :status="post.ai_status"
                :reject-reason="post.reject_reason"
              />
              <span
                class="post-card__tag post-card__tag--circle"
                :style="{
                  color: getCircleMeta(resolveCircleSlug(post)).pillColor,
                  background: getCircleMeta(resolveCircleSlug(post)).pillBg,
                }"
              >#{{ circleOf(post)?.name || post.category || '校园' }}</span>
            </div>
            <div v-else class="post-card__badges">
              <span
                class="post-card__tag post-card__tag--circle"
                :style="{
                  color: getCircleMeta(resolveCircleSlug(post)).pillColor,
                  background: getCircleMeta(resolveCircleSlug(post)).pillBg,
                }"
              >#{{ circleOf(post)?.name || post.category || '校园' }}</span>
            </div>

            <!-- 九宫图 / 视频（截图1是2列布局，给小宽度） -->
            <PostImages
              v-if="post.image_urls?.length || post.video_urls?.length"
              class="post-card__media post-card__media--moments"
              :urls="post.image_urls"
              :videos="post.video_urls"
            />

            <!-- 位置 -->
            <div v-if="post.location" class="post-card__location">
              <Icon name="map-pin" :size="12" /> {{ post.location }}
            </div>

            <!-- 底部：仅右侧一排「转发 点赞 评论」（左侧不再写死的多余0/计数器） -->
            <div class="post-card__foot">
              <button
                class="post-card__stat"
                :class="{ 'is-active': isLikedPost(post) }"
                type="button"
                @click="(e) => onSharePost(e, post)"
              >
                <Icon name="repeat" :size="18" />
                <span>{{ formatCount(post.share_count ?? 0) }}</span>
              </button>
              <button
                class="post-card__stat"
                :class="{ 'is-liked': isLikedPost(post) }"
                type="button"
                @click="(e) => onToggleLikePost(e, post)"
              >
                <!-- 点赞：已点赞填色心 -->
                <Icon :name="isLikedPost(post) ? 'heart-filled' : 'heart'" :size="18" />
                <span>{{ formatCount(post.like_count ?? 0) }}</span>
              </button>
              <button
                class="post-card__stat"
                type="button"
                @click="(e) => onOpenCommentInput(e, post)"
              >
                <Icon name="message-circle" :size="18" />
                <span>{{ formatCount(post.comment_count ?? 0) }}</span>
              </button>
            </div>"""

new_card = """            <!-- 顶部：头像 / 昵称-推荐时间 / 关注 / 更多 (图2朋友圈样式) -->
            <div class="post-card__head">
              <div class="post-card__avatar-wrap">
                <img
                  v-if="!post.is_anonymous && post.author_avatar_url"
                  class="post-card__avatar"
                  :src="post.author_avatar_url"
                  :alt="post.author"
                  loading="lazy"
                />
                <span
                  v-else
                  class="post-card__avatar post-card__avatar--ph"
                  :class="`av-${(post.author_id || 0) % 5 + 1}`"
                >{{ post.is_anonymous ? '匿' : (post.author || 'U').slice(0,1) }}</span>
                <!-- 头像右下角小标记（粉色♀符号） -->
                <span class="post-card__avatar-dot" aria-hidden="true">♀</span>
              </div>
              <div class="post-card__author-info">
                <div class="post-card__name-row">
                  <button
                    class="post-card__name-btn"
                    type="button"
                    @click="(e) => openAuthorHome(e, post)"
                  >{{ post.is_anonymous ? '匿名同学' : post.author }}</button>
                </div>
                <div class="post-card__sub">
                  <span>{{ formatRelativeTime(post.created_at) }}推荐</span>
                </div>
              </div>

              <div class="post-card__actions-top">
                <button
                  v-if="!post.is_anonymous && post.author_id && post.author_id !== session.userId"
                  class="post-card__follow"
                  :class="{ 'is-following': isFollowingAuthor(post) }"
                  type="button"
                  @click="(e) => onToggleFollowPostAuthor(e, post)"
                >
                  {{ isFollowingAuthor(post) ? '已关注' : '关注' }}
                </button>
                <button class="post-card__more" type="button" aria-label="更多">
                  <Icon name="more-horizontal" :size="20" />
                </button>
              </div>
            </div>

            <!-- 正文文字 -->
            <p v-if="post.content" class="post-card__text">{{ post.content }}</p>

            <!-- 图片/视频 (2列并排，圆角) -->
            <PostImages
              v-if="post.image_urls?.length || post.video_urls?.length"
              class="post-card__media"
              :urls="post.image_urls"
              :videos="post.video_urls"
            />

            <!-- 底部：分享/点赞/评论 均匀分布 -->
            <div class="post-card__foot">
              <button
                class="post-card__stat"
                type="button"
                @click="(e) => onSharePost(e, post)"
              >
                <Icon name="repeat" :size="20" />
                <span>{{ formatCount(post.share_count ?? 0) }}</span>
              </button>
              <button
                class="post-card__stat"
                :class="{ 'is-liked': isLikedPost(post) }"
                type="button"
                @click="(e) => onToggleLikePost(e, post)"
              >
                <Icon :name="isLikedPost(post) ? 'heart-filled' : 'heart'" :size="20" />
                <span>{{ formatCount(post.like_count ?? 0) }}</span>
              </button>
              <button
                class="post-card__stat"
                type="button"
                @click="(e) => onOpenCommentInput(e, post)"
              >
                <Icon name="message-circle" :size="20" />
                <span>{{ formatCount(post.comment_count ?? 0) }}</span>
              </button>
            </div>"""

s = s.replace(old_card_start, new_card)

p.write_text(s, encoding="utf-8")
print("OK: Card template replaced")
