/**
 * 双宠卡片内互动目录（≥30 种）
 * 每一条描述"我的宠物飞到对方卡片里，和对方宠物一起做的互动"。
 * - emoji：互动图标（气泡/动作示意）
 * - mine / theirs：互动过程中各自播放的动作 key（缺省回退待机）
 * - text：互动台词（会显示在气泡里，可用 {mine} / {theirs} 占位替换为宠物名）
 */
export interface PetInteraction {
  key: string
  emoji: string
  mine: string
  theirs: string
  text: string
}

export const PET_INTERACTIONS: PetInteraction[] = [
  { key: 'wave',      emoji: '👋',  mine: 'wave',    theirs: 'wave',    text: '{theirs}！出去兜风要不要~' },
  { key: 'hi5',       emoji: '✋',  mine: 'interact', theirs: 'interact', text: '击个掌！啪！' },
  { key: 'dance',     emoji: '💃',  mine: 'dance',   theirs: 'dance',   text: '一起跳舞！转圈圈！' },
  { key: 'sing',      emoji: '🎤',  mine: 'interact', theirs: 'interact', text: '来，跟我唱！拉拉拉~' },
  { key: 'share',     emoji: '🍖',  mine: 'eat',     theirs: 'eat',     text: '请你吃小零食~' },
  { key: 'coffee',    emoji: '☕',  mine: 'eat',     theirs: 'eat',     text: '干了这杯！' },
  { key: 'handshake', emoji: '🤝',  mine: 'interact', theirs: 'interact', text: '以后就是好朋友啦！' },
  { key: 'hug',       emoji: '🤗',  mine: 'interact', theirs: 'interact', text: '抱一下~' },
  { key: 'fight',     emoji: '🥊',  mine: 'attack',   theirs: 'attack',   text: '来比划比划！' },
  { key: 'wrestle',   emoji: '🤼',  mine: 'interact', theirs: 'interact', text: '摔跤决胜！' },
  { key: 'tag',       emoji: '🏃',  mine: 'walk',    theirs: 'walk',    text: '你追我！抓到啦！' },
  { key: 'flyrace',   emoji: '🐦',  mine: 'fly',     theirs: 'fly',     text: '比比谁飞得快！' },
  { key: 'jump',      emoji: '🤸',  mine: 'dance',   theirs: 'dance',   text: '一起蹦蹦跳跳！' },
  { key: 'spin',      emoji: '🌀',  mine: 'interact', theirs: 'interact', text: '转圈圈！晕了吗？' },
  { key: 'sleep',     emoji: '💤',  mine: 'sleep',   theirs: 'sleep',   text: '打个盹吧~' },
  { key: 'yawn',      emoji: '🥱',  mine: 'sleep',   theirs: 'interact', text: '哈欠传染了……' },
  { key: 'gossip',    emoji: '💬',  mine: 'interact', theirs: 'interact', text: '跟你说个小秘密……' },
  { key: 'laugh',     emoji: '😆',  mine: 'interact', theirs: 'dance',   text: '哈哈哈太好笑了~' },
  { key: 'apologize', emoji: '🙏',  mine: 'interact', theirs: 'interact', text: '对不起啦，原谅我~' },
  { key: 'tease',     emoji: '😜',  mine: 'interact', theirs: 'interact', text: '略略略~' },
  { key: 'mushroom',  emoji: '🍄',  mine: 'interact', theirs: 'interact', text: '看我采的蘑菇！' },
  { key: 'flower',    emoji: '🌸',  mine: 'interact', theirs: 'interact', text: '送你一朵花~' },
  { key: 'gift',      emoji: '🎁',  mine: 'interact', theirs: 'interact', text: '给你带了个礼物！' },
  { key: 'medal',     emoji: '🏅',  mine: 'dance',   theirs: 'interact', text: '你真棒，颁个奖！' },
  { key: 'triumph',   emoji: '🎉',  mine: 'dance',   theirs: 'dance',   text: '耶！我们赢啦！' },
  { key: 'peek',      emoji: '😳',  mine: 'interact', theirs: 'interact', text: '偷偷看一眼……' },
  { key: 'help',      emoji: '🆘',  mine: 'walk',    theirs: 'interact', text: '帮帮忙嘛！' },
  { key: 'pat',       emoji: '🫳',  mine: 'interact', theirs: 'interact', text: '摸摸头，乖~' },
  { key: 'rocket',    emoji: '🚀',  mine: 'fly',     theirs: 'fly',     text: '一起飞高高！' },
  { key: 'snowball',  emoji: '🫧',  mine: 'interact', theirs: 'interact', text: '吹个泡泡！' },
  { key: 'teaparty',  emoji: '🫖',  mine: 'eat',     theirs: 'eat',     text: '来杯下午茶~' },
  { key: 'camp',      emoji: '⛺',  mine: 'interact', theirs: 'interact', text: '今晚一起露营吧！' },
  { key: 'clap',      emoji: '👏',  mine: 'dance',   theirs: 'interact', text: '为你鼓掌！' },
  { key: 'confetti',  emoji: '🎊',  mine: 'dance',   theirs: 'dance',   text: '庆祝一下！' },
  { key: 'secretdial', emoji: '📞', mine: 'interact', theirs: 'interact', text: '密电联络中……' },
]

/** 随机取 n 种不重复的互动 */
export function pickInteractions(n = 3): PetInteraction[] {
  const pool = [...PET_INTERACTIONS]
  const out: PetInteraction[] = []
  while (out.length < n && pool.length) {
    const i = Math.floor(Math.random() * pool.length)
    out.push(pool.splice(i, 1)[0])
  }
  return out
}