import pathlib

p = pathlib.Path(r"d:/Users/Downloads/同伴圈/frontend/src/views/HomeView.vue")
s = p.read_text(encoding="utf-8")

# 1. Fix feedModeOf to return 'gatherings' for ALL tabs
old = """// P0-Bugfix：首页『为你推荐 / 游戏组局 / 现实组局』只展示组局(Gathering)，不包含广场帖子。
// 只有『全部』tab 继续走 postStore（广场帖子瀑布流）。
type FeedMode = 'posts' | 'gatherings'
function feedModeOf(key: FeedTabKey): FeedMode {
  return key === 'all' ? 'posts' : 'gatherings'
}"""

new = """// 所有 Tab 均展示组局/房间（单列圆角卡片），不再混入广场帖子
type FeedMode = 'posts' | 'gatherings'
function feedModeOf(_key: FeedTabKey): FeedMode {
  return 'gatherings'
}"""

s = s.replace(old, new)

p.write_text(s, encoding="utf-8")
print("OK: feedModeOf fixed")
