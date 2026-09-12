<template>
  <div class="os-page" ref="pageEl">
    <!-- Apple 风毛玻璃顶部导航 -->
    <header class="os-nav">
      <div class="os-nav-inner">
        <a class="os-logo" href="#top" @click.prevent="scrollTop">
          <img class="os-logo-mark" src="/xiguo/logo_mark.png" alt="西果集团 logo" />
          <span class="os-logo-text">西果集团</span>
        </a>
        <nav class="os-nav-links" aria-label="主导航">
          <a href="#products" @click.prevent="scrollTo('#products')">产品</a>
          <a href="#works" @click.prevent="scrollTo('#works')">作品</a>
          <a href="#about" @click.prevent="scrollTo('#about')">关于</a>
          <a href="#join" @click.prevent="scrollTo('#join')">加入我们</a>
        </nav>
        <div class="os-nav-actions">
          <a class="os-btn os-btn--primary" href="#products" @click.prevent="enterApp">进入同伴圈</a>
        </div>
      </div>
    </header>

    <div class="os-progress" aria-hidden="true"><span></span></div>

    <!-- Hero -->
    <section id="top" class="os-hero">
      <div class="os-hero-bg" aria-hidden="true">
        <span class="os-orb os-orb--1"></span>
        <span class="os-orb os-orb--2"></span>
        <span class="os-orb os-orb--3"></span>
      </div>
      <div class="os-hero-inner">
        <div class="os-hero-art" ref="heroArtEl">
          <img
            class="os-hero-img"
            src="/xiguo/hero_brand.png"
            alt="西果·校园数字生态品牌标志"
            decoding="async"
          />
        </div>
        <p class="os-eyebrow" data-reveal>西果集团 · 校园数字生态</p>
        <p class="os-hero-sub" data-reveal>
          同伴圈 · 接单大厅 · 作品集，一个账号，装下整个校园的灵感与温度。
        </p>
        <div class="os-hero-cta" data-reveal>
          <a class="os-btn os-btn--solid os-btn--lg" href="#products" @click.prevent="enterApp">
            打开同伴圈
          </a>
          <a class="os-btn os-btn--slate os-btn--lg os-btn--gradient" href="#products" @click.prevent="enterProject2">
            接单 · 把零花赚起来
          </a>
        </div>
      </div>
    </section>

    <!-- 产品入口 -->
    <section id="products" class="os-section os-section--light">
      <div class="os-container">
        <h2 class="os-section-title" data-reveal>我们的产品</h2>
        <p class="os-section-sub" data-reveal>一个账号，打通校园的每一个场景。</p>
        <div class="os-cards">
          <article class="os-card" data-reveal>
            <div class="os-card-media">
              <img
                src="/xiguo/product_community.jpg"
                alt="同伴圈产品图"
                loading="lazy"
                decoding="async"
              />
            </div>
            <h3 class="os-card-title">同伴圈</h3>
            <p class="os-card-desc">
              校园社区：帖子、圈子、漂流瓶、随机匹配、宠物养成与每日竞猜，让每份热爱都有人看见。
            </p>
            <div class="os-card-actions">
              <a class="os-btn os-btn--primary" href="#" @click.prevent="enterApp">立即进入</a>
              <a class="os-link" href="#works" @click.prevent="scrollTo('#works')">了解更多 →</a>
            </div>
          </article>
          <article class="os-card" data-reveal>
            <div class="os-card-media">
              <img
                src="/xiguo/product_orders.jpg"
                alt="接单大厅产品图"
                loading="lazy"
                decoding="async"
              />
            </div>
            <h3 class="os-card-title">接单大厅</h3>
            <p class="os-card-desc">
              求助 · 接单 · 完单：发任务、抢好单、安全交易币全程护航，合作一次，信任更多。
            </p>
            <div class="os-card-actions">
              <a class="os-btn os-btn--primary os-btn--solid" href="#" @click.prevent="enterProject2">进入大厅</a>
              <a class="os-link" href="#works" @click.prevent="scrollTo('#works')">了解更多 →</a>
            </div>
          </article>
        </div>
      </div>
    </section>

    <!-- 作品合集 -->
    <section id="works" class="os-section os-section--dark">
      <div class="os-container">
        <h2 class="os-section-title" data-reveal>作品合集</h2>
        <p class="os-section-sub" data-reveal>来自校园创作者的作品，正在被更多人看见。</p>
        <div class="os-showcase">
          <div
            v-for="(s, i) in showcase"
            :key="s.src"
            class="os-shot"
            :class="[`os-shot--${(i % 4) + 1}`, { 'os-shot--wide': s.wide }]"
            data-reveal
          >
            <div class="os-shot-stage">
              <figure class="os-shot-frame">
                <img :src="s.src" :alt="s.title" loading="lazy" decoding="async" />
              </figure>
              <figcaption class="os-shot-cap">
                <span class="os-shot-tag">{{ s.tag }}</span>
                <h3 class="os-shot-title">{{ s.title }}</h3>
                <p class="os-shot-desc">{{ s.desc }}</p>
              </figcaption>
            </div>
          </div>
        </div>
        <div class="os-showcase-cta" data-reveal>
          <a class="os-btn os-btn--solid os-btn--lg" href="#" @click.prevent="enterApp">进入同伴圈，亲自体验 →</a>
        </div>
      </div>
    </section>

    <!-- 关于 -->
    <section id="about" class="os-section os-section--light">
      <div class="os-container os-about">
        <div class="os-about-media" data-reveal>
          <img
            src="/xiguo/about.jpg"
            alt="西果团队工作坊"
            loading="lazy"
            decoding="async"
          />
        </div>
        <div class="os-about-body">
          <p class="os-eyebrow" data-reveal>关于西果</p>
          <h2 class="os-section-title os-section-title--left" data-reveal>把校园的小事，做成值得记住的作品。</h2>
          <p class="os-about-text" data-reveal>
            西果集团成立于公元2023年4月28日（癸卯年三月初十），全称西果集团农业科技有限公司，公司以“敢想、敢拼、敢干”为理念，铸就每一个梦想的实现，本公司涉及农业、科技等领域，以农业滋养科技，以科技造就农业，两者相辅相成，相得益彰。
          </p>
          <div class="os-stats" data-reveal>
            <div class="os-stat">
              <span class="os-stat-num" data-count="1000" data-count-suffix="+">0</span>
              <span class="os-stat-label">校园作品</span>
            </div>
            <div class="os-stat">
              <span class="os-stat-num" data-count="3">0</span>
              <span class="os-stat-label">核心产品</span>
            </div>
            <div class="os-stat">
              <span class="os-stat-num" data-count="24" data-count-suffix="h">0</span>
              <span class="os-stat-label">伙伴响应</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 加入我们 -->
    <section id="join" class="os-join">
      <div class="os-container os-join-inner">
        <h2 class="os-join-title">加入我们</h2>
        <p class="os-join-sub">无论你想创作、接单，还是把灵感变成产品，这里都有你的位置。</p>
        <div class="os-join-actions">
          <button class="os-btn os-btn--primary os-btn--lg" type="button" @click="enterApp">成为创作者</button>
          <button class="os-btn os-btn--primary os-btn--slate" type="button" @click="enterProject2">去接第一单</button>
        </div>
      </div>
    </section>

    <footer class="os-footer">
      <div class="os-container os-footer-inner">
        <p>© 2026 西果集团 Xiguo Group · 校园数字生态</p>
        <p><a href="#top" @click.prevent="scrollTop">返回顶部 ↑</a></p>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

gsap.registerPlugin(ScrollTrigger)

const router = useRouter()
const pageEl = ref<HTMLElement | null>(null)
const heroArtEl = ref<HTMLElement | null>(null)
const scrollY = ref(0)

const img = (prompt: string, size: string) =>
  `https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=${encodeURIComponent(prompt)}&image_size=${size}`

/** 画册式示意图：使用真实宣传截图，覆盖+裁剪，卡片化展示 */
const showcase = [
  { src: '/works/主页.png', title: '首页 · 广场', tag: '广场', desc: '瀑布流 + 今日竞猜 + 萌宠陪伴' },
  { src: '/works/发帖页面.png', title: '发帖创作', tag: '发布', desc: '图文 + 圈子 + 悬赏，一帖即发' },
  { src: '/works/圈子.png', title: '校园圈子', tag: '圈子', desc: '表白墙 / 求助区 / 游戏开黑' },
  { src: '/works/漂流瓶.png', title: '漂流瓶', tag: '玩法', desc: '匿名许愿，随机打捞缘分' },
  { src: '/works/帖子详情.png', title: '帖子详情', tag: '详情', desc: '宠物互动 + 回复专注体验' },
  { src: '/works/私聊界面.png', title: '私聊', tag: '社交', desc: '即时通讯，消息沉淀' },
  { src: '/works/表白墙.png', title: '表白墙', tag: '圈子', desc: '大声说出喜欢的名字' },
  { src: '/works/徽章.png', title: '徽章成就', tag: '成就', desc: '努力被看见，勋章加持' },
  { src: '/works/警告值.png', title: '社区安全', tag: '安全', desc: '透明信用，健康社区', wide: true },
]

/** 滚动进入视口时丝滑上浮/缩放/淡入（带错落延迟）+ 统计数字滚动 + Hero 视差 */
let io: IntersectionObserver | null = null
let stCleanup: (() => void) | null = null

function chooseDelay(el: HTMLElement): number {
  // 同组（同父容器）内的子元素按顺序错落；否则按全局取模错开
  const group = el.parentElement
  const siblings = group ? Array.from(group.children) : [el]
  const idx = siblings.indexOf(el)
  return (idx === -1 ? 0 : idx % 4) * 110
}

/** 预计算每个卡片应该从哪个方向进入 */
function initAnimations() {
  const root = pageEl.value
  if (!root || typeof IntersectionObserver === 'undefined') return
  root.querySelectorAll<HTMLElement>('[data-reveal]').forEach((el) => {
    const group = el.parentElement
    const siblings = group ? Array.from(group.children) : [el]
    const idx = Math.max(0, siblings.indexOf(el))
    const n = siblings.length
    // 同一行的卡片错落：从左到右、从下到上交错进入
    let fromPanel = (idx % 2 === 0 ? 'x' : 'xR') + (idx % 3 === 0 ? 'y' : 'yD')
    // Hero 区内容保持主轴居中对称，只做垂直入场（去掉横向偏移），避免标题在手机上不对称
    if (el.closest('.os-hero')) fromPanel = 'v'
    el.dataset.from = fromPanel
  })

  io = new IntersectionObserver(
    (entries) => {
      for (const en of entries) {
        if (en.isIntersecting) {
          const el = en.target as HTMLElement
          el.classList.add('os-in')
          if (el.dataset.count !== undefined) {
            runCounter(el, Number(el.dataset.count), el.dataset.countSuffix || '')
          }
          io?.unobserve(el)
        }
      }
    },
    { threshold: 0.16 },
  )

  root.querySelectorAll<HTMLElement>('[data-reveal]').forEach((el) => {
    el.style.transitionDelay = `${chooseDelay(el)}ms`
    io?.observe(el)
  })

  // 滚动视差与进度条驱动
  const onScroll = () => {
    scrollY.value = window.scrollY
    if (heroArtEl.value) {
      const y = window.scrollY
      heroArtEl.value.style.transform = `translate3d(0, ${y * 0.18}px, 0) scale(${Math.max(0.96, 1 - y / 2000)})`
    }
  }
  window.addEventListener('scroll', onScroll, { passive: true })
  onScrollCleanup = onScroll

  initGSAP(root)
}

/** GSAP：奢华视差/滚动触发动画（Awwwards 级） */
function initGSAP(root: HTMLElement) {
  const killers: (() => void)[] = []

  // 1) Hero 光球深度视差（不同速度的离析）
  const orbs = root.querySelectorAll<HTMLElement>('.os-orb')
  orbs.forEach((orb, i) => {
    const tween = gsap.to(orb, {
      yPercent: (i % 3 === 0 ? -38 : i % 3 === 1 ? 30 : -20),
      xPercent: (i % 2 === 0 ? -14 : 18),
      ease: 'none',
      scrollTrigger: { trigger: '.os-hero', start: 'top top', end: 'bottom top', scrub: 1 },
    })
    killers.push(() => tween.scrollTrigger?.kill() ?? tween.kill())
  })

  // 2) Hero 主标题已移除，不再需要主标题逐字浮起动画

  // 3) Hero 插画：打开即淡入（不依赖滚动触发，保证首屏立即可见）
  if (heroArtEl.value) {
    const tween = gsap.fromTo(
      heroArtEl.value,
      { opacity: 0 },
      { opacity: 1, duration: 0.45, ease: 'power1.out' },
    )
    killers.push(() => tween.kill())
  }

  // 4) 产品卡片：交错横向滚入 + 逐张收缩
  const cards = root.querySelectorAll<HTMLElement>('.os-card')
  cards.forEach((card, i) => {
    const tween = gsap.fromTo(
      card,
      { x: i % 2 === 0 ? -70 : 70, opacity: 0, y: 26, rotate: i % 2 === 0 ? -2 : 2 },
      {
        x: 0,
        opacity: 1,
        y: 0,
        rotate: 0,
        duration: 1,
        stagger: 0.1,
        ease: 'power3.out',
        scrollTrigger: { trigger: card, start: 'top 88%', toggleActions: 'play none none none' },
      },
    )
    killers.push(() => tween.scrollTrigger?.kill() ?? tween.kill())
  })

  // 5) 宣传作品墙：错落淡入（去掉图片内部纵向视差，避免图片下移露出黑底）
  root.querySelectorAll<HTMLElement>('.os-shot').forEach((shot, i) => {
    const tilt = gsap.fromTo(
      shot,
      { y: 44, opacity: 0 },
      {
        y: 0,
        opacity: 1,
        duration: 0.9,
        delay: i * 0.04,
        ease: 'power3.out',
        scrollTrigger: { trigger: shot, start: 'top 94%', toggleActions: 'play none none none' },
      },
    )
    killers.push(() => tilt.scrollTrigger?.kill() ?? tilt.kill())
  })

  // 6) 关于区：左右汇合
  const aboutMedia = root.querySelector<HTMLElement>('.os-about-media')
  const aboutBody = root.querySelector<HTMLElement>('.os-about-body')
  if (aboutMedia) {
    const t = gsap.fromTo(
      aboutMedia,
      { x: -70, opacity: 0 },
      { x: 0, opacity: 1, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: '.os-about', start: 'top 82%', toggleActions: 'play none none none' } },
    )
    killers.push(() => t.scrollTrigger?.kill() ?? t.kill())
  }
  if (aboutBody) {
    const t = gsap.fromTo(
      aboutBody,
      { x: 70, opacity: 0 },
      { x: 0, opacity: 1, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: '.os-about', start: 'top 82%', toggleActions: 'play none none none' } },
    )
    killers.push(() => t.scrollTrigger?.kill() ?? t.kill())
  }

  // 7) 顶部进度条联动滚动
  const progress = root.querySelector<HTMLElement>('.os-progress span')
  if (progress) {
    const t = gsap.to(progress, {
      scaleX: 1,
      ease: 'none',
      scrollTrigger: { trigger: '.os-page', start: 'top top', end: 'bottom bottom', scrub: 0.3 },
    })
    killers.push(() => t.scrollTrigger?.kill() ?? t.kill())
  }

  stCleanup = () => killers.forEach((k) => k())
}

function runCounter(el: HTMLElement, to: number, suffix = '') {
  const dur = 1500
  const start = performance.now()
  const step = (now: number) => {
    const p = Math.min(1, (now - start) / dur)
    const eased = 1 - Math.pow(1 - p, 3)
    el.textContent = `${Math.round(to * eased)}${suffix}`
    if (p < 1) requestAnimationFrame(step)
  }
  requestAnimationFrame(step)
}

let onScrollCleanup: (() => void) | null = null

function scrollTop() {
  pageEl.value?.scrollIntoView({ behavior: 'smooth' })
}
function scrollTo(sel: string) {
  const el = document.querySelector<HTMLElement>(sel)
  el?.scrollIntoView({ behavior: 'smooth' })
}
function enterApp() {
  router.push('/')
}
function enterProject2() {
  router.push('/orders')
}

onMounted(() => {
  initAnimations()
  // 首屏（Hero）元素直接播放进入动画；其余交给 IntersectionObserver 滚动触发
  requestAnimationFrame(() => {
    const hero = pageEl.value?.querySelector('.os-hero')
    hero?.querySelectorAll<HTMLElement>('[data-reveal]').forEach((el) => {
      const t = el as HTMLElement
      const group = el.parentElement
      const siblings = group ? Array.from(group.children) : [el]
      const idx = Math.max(0, siblings.indexOf(el))
      t.style.transitionDelay = `${(idx % 4) * 90}ms`
      setTimeout(() => t.classList.add('os-in'), 40)
    })
  })
})
onBeforeUnmount(() => {
  io?.disconnect()
  if (onScrollCleanup) window.removeEventListener('scroll', onScrollCleanup)
  if (stCleanup) {
    stCleanup()
    stCleanup = null
  }
})
</script>

<style scoped>
.os-page {
  --os-blue: #0071e3;
  --os-ink: #1d1d1f;
  --os-sub: #6e6e73;
  --os-bg: #f5f5f7;
  --os-ease: cubic-bezier(0.22, 1, 0.36, 1);
  background: var(--os-bg);
  color: var(--os-ink);
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', Arial, sans-serif;
  scroll-behavior: smooth;
  min-height: 100vh;
  overflow-x: hidden;
}

/* 顶部滚动进度条 */
.os-progress {
  position: fixed;
  top: 0;
  left: 0;
  height: 3px;
  width: 100%;
  z-index: 200;
  background: transparent;
}
.os-progress span {
  display: block;
  height: 100%;
  transform-origin: left center;
  background: linear-gradient(90deg, #0071e3, #5856d6 55%, #af52de);
  box-shadow: 0 0 12px rgba(88, 86, 214, 0.6);
  transition: transform 0.14s linear;
}

/* ===== 滚动进入动画：支持不同方向 + 缩放/模糊 弹入 ===== */
[data-reveal] {
  opacity: 0;
  will-change: transform, opacity, filter;
  transition: opacity 0.5s var(--os-ease), transform 0.5s var(--os-ease), filter 0.5s var(--os-ease);
}
[data-from='xy'] { transform: translate3d(-30px, 26px, 0) scale(0.96); filter: blur(6px); }
[data-from='xRy'] { transform: translate3d(30px, 26px, 0) scale(0.96); filter: blur(6px); }
[data-from='xyD'] { transform: translate3d(-30px, -26px, 0) scale(0.96); filter: blur(6px); }
[data-from='xRyD'] { transform: translate3d(30px, -26px, 0) scale(0.96); filter: blur(6px); }
[data-from='v'] { transform: translate3d(0, 30px, 0) scale(0.98); filter: blur(5px); }
[data-reveal]:not([data-from]) { transform: translate3d(0, 34px, 0); filter: blur(4px); }
.os-page [data-reveal].os-in {
  opacity: 1;
  transform: translate3d(0, 0, 0) scale(1);
  filter: blur(0);
}

/* 顶部导航 */
.os-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(245, 245, 247, 0.8);
  -webkit-backdrop-filter: saturate(1.8) blur(20px);
  backdrop-filter: saturate(1.8) blur(20px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}
.os-nav-inner {
  max-width: 1180px;
  margin: 0 auto;
  height: 52px;
  padding: 0 22px;
  display: flex;
  align-items: center;
  gap: 22px;
}
.os-logo {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--os-ink);
  text-decoration: none;
  font-size: 17px;
  font-weight: 700;
}
.os-logo-mark {
  height: 28px;
  width: auto;
  display: block;
  object-fit: contain;
}
.os-nav-links {
  display: flex;
  gap: 26px;
  margin-left: 8px;
}
.os-nav-links a {
  color: var(--os-sub);
  font-size: 15px;
  text-decoration: none;
  transition: color 0.15s ease;
}
.os-nav-links a:hover {
  color: var(--os-ink);
}
.os-nav-actions {
  margin-left: auto;
}
.os-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: 980px;
  cursor: pointer;
  font-size: 16px;
  padding: 9px 20px;
  text-decoration: none;
  border: 1px solid transparent;
  font-family: inherit;
  transition: background 0.15s ease, color 0.15s ease, transform 0.12s ease;
}
.os-btn--primary {
  background: transparent;
  color: var(--os-blue);
}
.os-btn--primary:hover {
  color: #0066cc;
  transform: translateY(-1px);
}
.os-btn--solid {
  background: linear-gradient(135deg, #0071e3, #0060cc);
  color: #fff;
  box-shadow: 0 8px 20px rgba(0, 113, 227, 0.28);
}
.os-btn--solid:hover {
  color: #fff;
  background: linear-gradient(135deg, #007aff, #0066d6);
  box-shadow: 0 12px 26px rgba(0, 113, 227, 0.34);
  transform: translateY(-1px);
}
.os-btn--solid:active {
  background: #0060cc;
  transform: translateY(0);
}
.os-btn--slate {
  background: #fff;
  color: var(--os-ink);
  border-color: rgba(0, 0, 0, 0.12);
}
.os-btn--slate:hover {
  background: #f0f0f2;
}
/* 发单·接单 分按钮：柔光渐变描边，白底描字，hover 仍清晰可读 */
.os-btn--gradient {
  background: #fff;
  color: #5856d6;
  border: 1px solid rgba(88, 86, 214, 0.35);
  box-shadow: 0 8px 20px rgba(88, 86, 214, 0.14);
}
.os-btn--gradient:hover {
  color: #4a48c7;
  background: linear-gradient(135deg, #ffffff, #eef1ff);
  border-color: rgba(88, 86, 214, 0.55);
  transform: translateY(-1px);
}
.os-btn--lg {
  padding: 13px 26px;
  font-size: 17px;
}

/* Hero */
.os-hero {
  position: relative;
  overflow: hidden;
  text-align: center;
  /* 首屏大图位于顶部，顶距只需清开导航即可；下方文字由图片底距推进 */
  padding: 96px 22px 40px;
}
.os-hero-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
}
.os-hero-bg::before {
  content: '';
  position: absolute;
  inset: -40% -30%;
  background:
    radial-gradient(58% 46% at 20% 16%, rgba(0, 113, 227, 0.18), transparent 62%),
    radial-gradient(50% 40% at 82% 12%, rgba(88, 86, 214, 0.2), transparent 62%),
    radial-gradient(70% 60% at 50% 110%, rgba(0, 113, 227, 0.12), transparent 64%);
  animation: os-drift 26s ease-in-out infinite alternate;
}
.os-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(2px);
  opacity: 0.7;
}
.os-orb--1 {
  width: 420px;
  height: 420px;
  top: 6%;
  left: 4%;
  background: radial-gradient(circle at 32% 30%, rgba(0, 113, 227, 0.34), rgba(0, 113, 227, 0) 68%);
  animation: os-float-1 16s ease-in-out infinite;
}
.os-orb--2 {
  width: 320px;
  height: 320px;
  bottom: 12%;
  right: 8%;
  background: radial-gradient(circle at 60% 40%, rgba(88, 86, 214, 0.32), rgba(88, 86, 214, 0) 68%);
  animation: os-float-2 20s ease-in-out infinite;
}
.os-orb--3 {
  width: 220px;
  height: 220px;
  top: 58%;
  left: 22%;
  background: radial-gradient(circle at 45% 50%, rgba(175, 82, 222, 0.28), rgba(175, 82, 222, 0) 68%);
  animation: os-float-3 13s ease-in-out infinite;
}
@keyframes os-drift {
  0% { transform: translate3d(-3%, -2%, 0) scale(1); }
  100% { transform: translate3d(3%, 3%, 0) scale(1.12); }
}
@keyframes os-float-1 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(28px, -16px) scale(1.06); }
  66% { transform: translate(-16px, 20px) scale(0.97); }
}
@keyframes os-float-2 {
  0%, 100% { transform: translate(0, 0) scale(1) rotate(0deg); }
  50% { transform: translate(-24px, -20px) scale(1.05) rotate(8deg); }
}
@keyframes os-float-3 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(20px, 22px) scale(1.08); }
}
.os-hero-inner {
  position: relative;
  z-index: 1;
  max-width: 1180px;
  margin: 0 auto;
}
.os-eyebrow {
  font-size: 15px;
  font-weight: 600;
  color: var(--os-blue);
  letter-spacing: 0.04em;
  margin: 0 0 28px;
}
.os-hero-sub {
  font-size: clamp(17px, 2.4vw, 28px);
  line-height: 1.28;
  color: var(--os-sub);
  max-width: 640px;
  margin: 22px auto 0;
}
.os-hero-cta {
  margin-top: 34px;
  display: flex;
  justify-content: center;
  gap: 14px;
  flex-wrap: wrap;
}
/* Hero 主视觉大图横幅（透明品牌标：位于顶部、居中、不裁剪、不去卡片化圆角投影） */
.os-hero-art {
  margin: 0 auto 44px;
  display: flex;
  justify-content: center;
}
.os-hero-img {
  display: block;
  margin: 0 auto;
  width: auto;
  max-width: min(92%, 560px);
  max-height: min(46vh, 460px);
  object-fit: contain;
}

/* 通用 section */
.os-section {
  padding: 100px 22px;
  scroll-margin-top: 60px;
}
.os-section--light {
  background: #fff;
}
.os-section--dark {
  background: #000;
  color: #fff;
}
.os-container {
  max-width: 1180px;
  margin: 0 auto;
}
.os-section-title {
  font-size: clamp(30px, 4.4vw, 56px);
  line-height: 1.05;
  font-weight: 700;
  letter-spacing: -0.015em;
  text-align: center;
  margin: 0;
}
.os-section-title--left {
  text-align: left;
}
.os-section-sub {
  text-align: center;
  color: var(--os-sub);
  font-size: 18px;
  margin: 14px auto 48px;
  max-width: 560px;
}
.os-section--dark .os-section-sub {
  color: #a1a1a6;
}

/* 产品卡片 */
.os-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 26px;
}
.os-card {
  background: var(--os-bg);
  border-radius: 24px;
  overflow: hidden;
  padding: 18px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.os-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 16px 30px rgba(0, 0, 0, 0.1);
}
.os-card-media {
  border-radius: 18px;
  overflow: hidden;
}
.os-card-media img {
  width: 100%;
  height: 180px;
  object-fit: cover;
  display: block;
}
.os-card-title {
  font-size: 24px;
  font-weight: 700;
  margin: 18px 6px 8px;
}
.os-card-desc {
  color: var(--os-sub);
  font-size: 15px;
  line-height: 1.55;
  margin: 0 6px;
  flex: 1;
}
.os-card-actions {
  margin: 18px 6px 4px;
  display: flex;
  align-items: center;
  gap: 16px;
}
.os-link {
  color: var(--os-blue);
  text-decoration: none;
  font-size: 15px;
}
.os-link:hover {
  color: #0066cc;
  text-decoration: underline;
}

/* 作品/示意图：适配手机端的简洁卡片瀑布 */
.os-showcase {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 14px;
  margin-top: 40px;
}
.os-shot {
  --os-shot-grad: linear-gradient(140deg, #1b1b24, #2a2a3a);
  position: relative;
  border-radius: 20px;
  overflow: hidden;
  background: #101014;
  box-shadow: 0 12px 26px rgba(0, 0, 0, 0.35);
  transition: transform 0.3s var(--os-ease), box-shadow 0.3s var(--os-ease);
}
.os-shot--1 { --os-shot-grad: linear-gradient(140deg, #171d2b, #283a63); }
.os-shot--2 { --os-shot-grad: linear-gradient(140deg, #231b31, #46307a); }
.os-shot--3 { --os-shot-grad: linear-gradient(140deg, #1c2620, #2f6043); }
.os-shot--4 { --os-shot-grad: linear-gradient(140deg, #2b1b1b, #7a3a30); }

.os-shot:hover {
  transform: translateY(-5px);
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
}
/* 手机截图：完整显示、不裁剪、不溢出 */
.os-shot-frame {
  position: relative;
  margin: 0;
  width: 100%;
  aspect-ratio: 11 / 20;
  overflow: hidden;
  background: #000;
}
.os-shot-frame img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: top center;
}
/* 横版截图（社区安全）：占两列、用横画幅，完整显示不被裁切 */
.os-shot--wide {
  grid-column: span 2;
}
.os-shot--wide .os-shot-frame {
  aspect-ratio: 2 / 1;
}
.os-shot--wide .os-shot-frame img {
  object-position: center;
}
.os-shot-cap {
  padding: 14px 14px 16px;
  color: #fff;
  background: linear-gradient(140deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0));
}
.os-shot-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  color: #b9c7ff;
  background: rgba(255, 255, 255, 0.12);
  padding: 3px 10px;
  border-radius: 999px;
}
.os-shot-title {
  font-size: 16px;
  font-weight: 700;
  margin: 8px 0 3px;
}
.os-shot-desc {
  color: #c7c7d2;
  font-size: 12px;
  line-height: 1.5;
  margin: 0;
}
.os-showcase-cta {
  margin-top: 40px;
  text-align: center;
}

/* 桌面：作品卡片更大一档，横排 3~4 列 */
@media (min-width: 720px) {
  .os-showcase {
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 22px;
  }
  .os-shot-frame {
    aspect-ratio: 9 / 16;
  }
}

/* 关于 */
.os-about {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 54px;
  align-items: center;
}
.os-about-media img {
  width: 100%;
  max-height: 540px;
  object-fit: cover;
  object-position: top center;
  border-radius: 24px;
  box-shadow: 0 20px 44px rgba(0, 0, 0, 0.1);
}
.os-about-body {
  text-align: left;
}
.os-about-text {
  color: var(--os-sub);
  font-size: 16px;
  line-height: 1.7;
  margin: 20px 0 28px;
}
.os-stats {
  display: flex;
  gap: 36px;
}
.os-stat-num {
  display: block;
  font-size: 34px;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.os-stat-label {
  color: var(--os-sub);
  font-size: 14px;
}

/* 加入我们 */
.os-join {
  background: linear-gradient(120deg, #111118, #1d1d2a);
  color: #fff;
  padding: 110px 22px;
  text-align: center;
}
.os-join-title {
  font-size: clamp(32px, 5vw, 64px);
  font-weight: 700;
  letter-spacing: -0.02em;
  margin: 0;
}
.os-join-sub {
  color: #a1a1a6;
  font-size: 18px;
  max-width: 520px;
  margin: 16px auto 34px;
}
.os-join-actions {
  display: flex;
  justify-content: center;
  gap: 14px;
  flex-wrap: wrap;
}

/* Footer */
.os-footer {
  background: #f5f5f7;
  color: var(--os-sub);
  font-size: 13px;
  padding: 34px 22px;
  text-align: center;
}
.os-footer p {
  margin: 4px 0;
}
.os-footer a {
  color: var(--os-sub);
  text-decoration: none;
}
.os-footer a:hover {
  color: var(--os-ink);
}

@media (max-width: 820px) {
  .os-nav-links {
    display: none;
  }
  .os-nav-actions .os-btn {
    font-size: 14px;
    padding: 8px 15px;
  }
  .os-about {
    grid-template-columns: 1fr;
    gap: 30px;
  }
  .os-stats {
    gap: 24px;
    flex-wrap: wrap;
  }
  .os-section {
    padding: 64px 18px;
  }
  .os-hero {
    padding-top: 64px;
  }
}

/* 手机窄屏：标题分级缩放、整体垂直收紧，让大图在首屏露出；杜绝文字重合 */
@media (max-width: 540px) {
  .os-hero {
    /* 顶部留白按“导航高度 + 间距”计算，保证标题两行落在导航下方的安全区 */
    padding: calc(52px + 30px) 16px 22px;
  }
  .os-eyebrow {
    font-size: 13px;
  }
  .os-hero-sub {
    font-size: 15px;
    line-height: 1.5;
    margin-top: 14px;
  }
  .os-hero-cta {
    margin-top: 24px;
    gap: 10px;
  }
  .os-hero-cta .os-btn {
    width: 100%;
    max-width: 320px;
    justify-content: center;
    text-align: center;
  }
  .os-hero-art {
    margin: 0 auto 28px;
  }
  /* 透明品牌标：保持居中、不裁剪文字 */
  .os-hero-img {
    border-radius: 0;
    max-height: min(28vh, 300px);
    object-fit: contain;
    object-position: center;
  }
  .os-btn--lg {
    padding: 12px 18px;
    font-size: 15px;
  }
  .os-section-title {
    line-height: 1.12;
  }
  /* 导航靠左贴合，防止右侧按钮溢出台边 */
  .os-nav-inner {
    padding: 0 14px;
    gap: 10px;
  }
}
</style>