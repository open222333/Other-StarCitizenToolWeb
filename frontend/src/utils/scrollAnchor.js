// 換頁後把列表頂端捲回畫面。
// 換頁時列表會先變成「載入中」一行，頁面瞬間變短，瀏覽器為了讓焦點（剛按的分頁按鈕）留在原位，
// 新資料載入後畫面就停在最下方的分頁按鈕那裡。列表頂端已經捲出畫面（或被固定的頂端列蓋住）時才捲回去。
// 元素要加 class="sf-scroll-anchor"（scroll-margin-top 留出固定頂端列的高度，見 scifi-theme.css）。
import { nextTick } from 'vue'

export async function scrollToListTop(el) {
  await nextTick()
  if (!el || typeof el.getBoundingClientRect !== 'function') return
  const margin = parseFloat(getComputedStyle(el).scrollMarginTop) || 0
  if (el.getBoundingClientRect().top < margin) el.scrollIntoView({ block: 'start', behavior: 'smooth' })
}
