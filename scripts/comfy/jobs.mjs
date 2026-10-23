// 生成任务：首帧、尾帧（cyan 关键帧的状态名）、帧数、动作提示词。
// MiniMax H3 的帧数必须是 17k+5：124 帧 ≈ 5.17 秒，56 帧 ≈ 2.33 秒，73 帧 ≈ 3.04 秒。

import { SKIN } from './skin.mjs'

export const LOOP_FRAMES = 124
export const TRANSITION_FRAMES = 56

// 模型有时会自己“剪辑”（切到脸部特写再切回来），所有片段开头都强调单一镜头。
export const SHOT_PROMPT = '单一连续镜头，固定机位，角色全身始终完整地在画面中，画面不切换、不推近、不出现任何特写，纯青色背景全程不变。'

// 桌宠目前没有说话功能：任何片段都不能张嘴。
export const COMMON_PROMPT =
  (SKIN === 'chibi' ? '。Q版三头身角色，全程保持Q版比例和面无表情的冷淡神情（冷脸萌）' : '') +
  '。二次元动漫风格。固定镜头、无缩放；纯青色背景保持不变；角色、服装、书堆和人物大小保持稳定；面部表情保持和第一帧一致，嘴唇始终闭合，不张嘴、不说话、不笑出声；无多余手指、无闪烁、无突然跳变、无道具消失。'

const NO_PAGE_TURN = '绝对不要翻页，书页和双手保持原位。'

/**
 * 现在所有 loop 都用 single（一段 K0 → K0）。K1 和 A/B 两段的写法保留，但不再使用：
 * 两段各自随机生成，动作幅度和速度经常差很多。
 *
 * loop 有两种做法：
 * - single：一段 K0 → K0，一个连续的动作，节奏和幅度一致（提示词里不能有“来回”的描述）。
 * - K0 → K1 → K0 两段拼接：动作更丰富，但两段的幅度和速度无法控制一致。
 * finish.py 优先使用 single 段（任务名 <状态>-L）。
 */
const LOOPS = {
  // 动作幅度参照用户选定的 idle（idle-L2）：头随呼吸轻轻歪一下，身体晃动明显一些
  idle: {
    k0: 'hub-A-approved',
    // idle 的嘴应该一直闭着；随机事件（打哈欠）不继承这个坐标
    k1: 'idle-mid',
    single:
      '她安静地坐着，自然地呼吸：缓慢吸气时胸口和肩膀微微抬起，再缓缓呼气落下，身体随着呼吸轻轻地晃动，发丝轻轻飘动，中途自然地眨一次眼；头随着呼吸轻轻地歪一下再回正，不抬头也不低头，嘴巴始终闭合，表情平静不变，双手与合起的书保持不动',
    // idle 只要轻微的呼吸和晃动，不要明显的抬头低头
    a: '她安静地坐着，缓慢地吸气，胸口和肩膀随呼吸微微抬起，身体极轻微地向一侧晃动，发丝轻轻飘动；头随着呼吸轻轻地歪一下再回正，不抬头也不低头，嘴巴闭合，表情平静不变，双手与合起的书保持不动',
    b: '她缓慢地呼气，胸口和肩膀微微落下，身体轻轻晃回原位，自然地眨一下眼；头随着呼吸轻轻地歪一下再回正，不抬头也不低头，嘴巴闭合，表情平静不变，手和书不动'
  },
  thinking: {
    k0: 'thinking',
    single: '她指尖轻轻抵着下巴，保持思考的姿势，视线微微游移、若有所思，自然地呼吸，身体随着呼吸轻轻地晃动，中途自然地眨一次眼；头随着呼吸轻轻地歪一下再回正，嘴巴始终闭合，表情平静，手的位置保持不变',
    k1: 'thinking-mid',
    a: '视线缓慢移向画面左上方，指尖轻轻抵住下巴，思索逐渐加深',
    b: '她像突然想到一点线索般轻轻点一下头，视线回到原位，手指仍在下巴'
  },
  reading: {
    k0: 'reading',
    single: '她低头安静地读着摊开的书，视线沿着书页缓缓移动，自然地呼吸，身体随着呼吸轻轻地晃动，中途自然地眨一次眼；头随着呼吸轻轻地歪一下再回正，嘴巴始终闭合，手、书和翘起的页角完全不动，绝对不要翻页',
    k1: 'reading-mid',
    a: `视线沿当前书页缓慢向下移动；手、书和已经翘起的页角完全不动。${NO_PAGE_TURN}`,
    b: `视线较快地跳回同一页的上方，准备接着读。${NO_PAGE_TURN}`
  },
  writing: {
    k0: 'writing',
    single: '她用羽毛笔在书页上慢慢地书写，笔尖只做很小幅度的移动，另一只手扶着书页，自然地呼吸，中途自然地眨一次眼；头随着呼吸轻轻地歪一下再回正，嘴巴始终闭合，书本保持不动',
    k1: 'writing-mid',
    a: '羽毛笔笔尖沿同一行缓慢向右写到行尾，另一只手固定书页',
    b: '笔尖离纸一点点，较快移回下一行行首，再轻轻落笔；书本与另一只手不动'
  },
  confirmation: {
    k0: 'waiting-confirmation',
    // “望向观众”“询问”会让模型以为在说话；只描述姿势，嘴唇紧紧抿着
    single: '她举着一只手，歪着头安静地坐着，自然地呼吸，身体随着呼吸轻轻地晃动，中途自然地眨一次眼；举起的手保持在原位只微微晃动，头随着呼吸轻轻地歪一下再回正，嘴唇紧紧抿着',
    k1: 'confirmation-mid',
    a: '她轻轻歪头看向观众，眼神带一点询问；举起的手仅微微晃动',
    b: '她眨一下眼，露出浅笑，头回正；举起的手回到原来的位置'
  },
  // complete 原本是一次性状态，现在 Stop 后要保持一段时间，所以也需要 loop
  complete: {
    k0: 'complete',
    single:
      // “满足”“微笑”这类词会被理解成开口大笑，只描述动作，并要求表情和第一帧保持一致
      '她把合起的书抱在胸前安静地坐着，自然地呼吸，身体随着呼吸轻轻地晃动，发丝轻轻飘动，中途自然地眨一次眼；头随着呼吸轻轻地歪一下再回正；面部表情全程和第一帧完全一样，嘴唇一直闭合，不做任何表情变化；双手抱书的姿势保持不动'
  },
  drowsy: {
    k0: 'drowsy',
    single: '她闭着眼睛打瞌睡，随着缓慢深沉的呼吸，头极轻微地一点一点，身体轻轻晃动，发丝轻轻飘动；眼睛始终闭着，嘴巴始终闭合，手和书保持不动',
    k1: 'drowsy-mid',
    a: '她闭着眼，头很慢地向下垂，像快睡着了；手和书不动',
    b: '头轻轻一点，似乎稍微惊醒，再缓缓回到原来的打盹姿势'
  }
}

export const JOBS = {}
for (const [state, l] of Object.entries(LOOPS)) {
  if (l.k1) {
    JOBS[`${state}-A`] = { state, segment: 'A', first: l.k0, last: l.k1, frames: LOOP_FRAMES, prompt: l.a }
    JOBS[`${state}-B`] = { state, segment: 'B', first: l.k1, last: l.k0, frames: LOOP_FRAMES, prompt: l.b }
  }
  if (l.single) {
    JOBS[`${state}-L`] = { state, segment: 'L', first: l.k0, last: l.k0, frames: LOOP_FRAMES, prompt: l.single }
    // 同一提示词、不同随机种子的变体（L2、L3…），引擎每轮随机挑一段播放，减轻循环感。
    // 注意：一次生成 243 帧（10 秒）时模型会自己切镜头（切到书的特写），不可用。
    for (let v = 2; v <= 4; v++)
      JOBS[`${state}-L${v}`] = {
        state,
        segment: `L${v}`,
        first: l.k0,
        last: l.k0,
        frames: LOOP_FRAMES,
        prompt: l.single,
        // 变体输出到单独的文件，manifest 里登记为 <状态>-loop-<v>
        out: `claude-girl-loop-${state}-${v}-transparent-9x16.webm`
      }
  }
}

/**
 * 过渡片段：枢纽 ↔ 状态、枢纽 A ↔ B。首尾帧都是现有 K0，时长 2–3 秒。
 * file 是 resources/assets/videos/transitions/ 下的文件名主体。
 */
const TRANSITIONS = {
  'hub-A-to-B': { first: 'hub-A-approved', last: 'hub-B-approved', frames: 73, prompt: '她双手把膝上合着的书翻开，书摊开在膝上，视线落到书页上' },
  'hub-B-to-A': { first: 'hub-B-approved', last: 'hub-A-approved', frames: 73, prompt: '她合上膝上摊开的书，双手轻放在合起的书上，抬起视线' },
  'thinking-hub-to-state': { first: 'hub-A-approved', last: 'thinking', frames: 56, prompt: '她抬起右手，指尖轻轻抵住下巴，视线移向上方，陷入思考；书仍合着放在膝上' },
  'thinking-state-to-hub': { first: 'thinking', last: 'hub-A-approved', frames: 56, prompt: '她放下抵着下巴的手，视线回到前方，双手回到膝上合着的书上' },
  'confirmation-hub-to-state': { first: 'hub-A-approved', last: 'waiting-confirmation', frames: 56, prompt: '她抬起一只手，掌心朝向观众，歪头看向观众，像在询问可不可以' },
  'confirmation-state-to-hub': { first: 'waiting-confirmation', last: 'hub-A-approved', frames: 56, prompt: '她放下举起的手，双手回到膝上合着的书上，恢复安静的坐姿' },
  'complete-hub-to-state': { first: 'hub-A-approved', last: 'complete', frames: 73, prompt: '她开心地拿起膝上合着的书，抱在胸前，露出满足的微笑' },
  'complete-state-to-hub': { first: 'complete', last: 'hub-A-approved', frames: 73, prompt: '她把抱在胸前的书轻轻放回膝上，双手放在书上，神情平静' },
  'error-hub-to-state': { first: 'hub-A-approved', last: 'error-v3', frames: 73, prompt: '她吃了一惊，慌张地把书举到胸前，表情有些不知所措' },
  'error-state-to-hub': { first: 'error-v3', last: 'hub-A-approved', frames: 73, prompt: '她松了一口气，把书放回膝上，双手放在书上，表情恢复平静' },
  // Q 版的 error 是抱头蹲防（关键帧 chibi-error），见下面的覆盖
  'drowsy-hub-to-state': { first: 'hub-A-approved', last: 'drowsy', frames: 56, prompt: '她慢慢闭上眼睛，头轻轻歪向一侧，开始打瞌睡；手和书不动' },
  'drowsy-state-to-hub': { first: 'drowsy', last: 'hub-A-approved', frames: 56, prompt: '她慢慢睁开眼睛，头回正，清醒过来；手和书不动' },
  'reading-hub-to-state': { first: 'hub-B-approved', last: 'reading', frames: 56, prompt: `她低下头看向摊开的书，开始阅读。${NO_PAGE_TURN}` },
  'reading-state-to-hub': { first: 'reading', last: 'hub-B-approved', frames: 56, prompt: `她从书页上抬起视线，回到平静的坐姿，书仍摊开在膝上。${NO_PAGE_TURN}` },
  // writing 关键帧的书是平放、书页朝上的，枢纽 B 的书更立起来一些，过渡里要把书放平 / 扶回
  'writing-hub-to-state': { first: 'hub-B-approved', last: 'writing', frames: 56, prompt: '她把膝上摊开的书轻轻放平，书页朝上，然后拿起羽毛笔，在书页上轻轻落笔' },
  'writing-state-to-hub': { first: 'writing', last: 'hub-B-approved', frames: 56, prompt: '她放下羽毛笔，双手扶着摊开的书，把书稍稍立起来一些，回到捧书的姿势' }
}

if (SKIN === 'chibi') {
  TRANSITIONS['error-hub-to-state'] = {
    first: 'hub-A-approved',
    last: 'error',
    frames: 73,
    prompt: '她被吓了一跳，立刻用双手紧紧抱住脑袋，缩着脖子蜷成一团（抱头蹲防），眼睛紧紧闭上，表情委屈又慌张'
  }
  TRANSITIONS['error-state-to-hub'] = {
    first: 'error',
    last: 'hub-A-approved',
    frames: 73,
    prompt: '她偷偷睁开一只眼睛看了看，确认没事后慢慢松开抱着脑袋的双手，若无其事地坐正，双手放回膝上的书上，恢复冷淡的表情'
  }
}
// 直达过渡：工作中最常切换的三个状态之间直接过去，不再“退场 → 回枢纽 → 换枢纽 → 进场”绕三段（思考 → 写代码原来要 15.5 秒）。
// manifest 里登记为 type "direct"，from / to 是状态名；引擎按最短路径走，自然会选它
Object.assign(TRANSITIONS, {
  'thinking-to-reading': { first: 'thinking', last: 'reading', frames: 56, prompt: `她放下抵着下巴的手，把膝上合着的书打开，双手捧着摊开的书，低头开始阅读，书打开后不再翻页` },
  'reading-to-thinking': { first: 'reading', last: 'thinking', frames: 56, prompt: '她从书页上抬起视线，把书合上放回膝上，抬起右手用食指轻轻抵住下巴，若有所思' },
  'thinking-to-writing': { first: 'thinking', last: 'writing', frames: 56, prompt: '她放下抵着下巴的手，把膝上的书打开平放，书页朝上，然后拿起羽毛笔，在书页上轻轻落笔' },
  'writing-to-thinking': { first: 'writing', last: 'thinking', frames: 56, prompt: '她放下羽毛笔，合上书放回膝上，抬起右手用食指轻轻抵住下巴，若有所思' },
  'reading-to-writing': { first: 'reading', last: 'writing', frames: 56, prompt: `她把摊开的书轻轻放平，书页朝上，拿起羽毛笔，在书页上轻轻落笔，不要翻页` },
  'writing-to-reading': { first: 'writing', last: 'reading', frames: 56, prompt: `她放下羽毛笔，双手捧起摊开的书，把书稍稍立起来，低头阅读，不要翻页` }
})
for (const [file, t] of Object.entries(TRANSITIONS)) JOBS[`t-${file}`] = { transition: file, ...t }

/**
 * 过渡（第二版，任务名 T-<文件名>）：两端不再是静止的关键帧，而是用相邻 loop 的帧锚住。
 * 开头 22 帧 = 出发节点 loop 的开头，结尾 22 帧 = 到达节点 loop 的结尾，所以经过同一张关键帧的片段
 * 都是“像 loop 结尾那样到达、像 loop 开头那样离开”，怎么组合都带着动作接上。
 * error 是一次性状态（在关键帧上停留），那一端仍然锚单张关键帧。
 * 时长 124 帧：去掉两端各 22 帧的引导，中间约 3.3 秒是真正的过渡动作。
 */
const NODE_LOOP = {
  'hub-A-approved': 'idle',
  'hub-B-approved': 'hubB',
  thinking: 'thinking',
  reading: 'reading',
  writing: 'writing',
  'waiting-confirmation': 'confirmation',
  complete: 'complete',
  drowsy: 'drowsy'
}
const T_GUIDE = 22
// 动作幅度大的过渡加长，否则中间那一下会显得急（complete 抱书）
// Q 版 drowsy 进场 124 帧时两次都在中途硬切（整个人突然挪一截、眼睛一下闭上），加长给模型留出时间
const T_FRAMES = { 'complete-hub-to-state': 158, ...(SKIN === 'chibi' ? {} : { 'error-hub-to-state': 158 }), ...(SKIN === 'chibi' ? { 'drowsy-hub-to-state': 158 } : {}) }
const T_SLOW = { 'complete-hub-to-state': '整个动作放慢，轻柔地，', ...(SKIN === 'chibi' ? { 'drowsy-hub-to-state': '眼睛一点一点慢慢地合上，' } : {}) }
for (const [file, t] of Object.entries(TRANSITIONS)) {
  const from = NODE_LOOP[t.first]
  const to = NODE_LOOP[t.last]
  JOBS[`T-${file}`] = {
    transition: file,
    first: t.first,
    last: t.last,
    frames: T_FRAMES[file] ?? 124,
    guides: [
      // 一次性状态（error）那一端锚 5 帧相同的关键帧：只锚一张的话最后一帧会跳一下，起步也太猛
      from ? { from: `${from}-ML`, start: 0, count: T_GUIDE, at: 0 } : { image: t.first, at: 0, repeat: 5 },
      to ? { from: `${to}-ML`, start: -T_GUIDE, count: T_GUIDE, at: -T_GUIDE } : { image: t.last, at: -5, repeat: 5 }
    ],
    prompt:
      (from ? '开头她还在轻轻摇晃，接着' : '开头她静止不动，然后慢慢地') +
      (T_SLOW[file] ?? '') +
      `${t.prompt}，动作从容、不急不慢，没有动作模糊` +
      (to ? '，最后自然地回到轻轻摇晃' : '，最后慢慢停下来，静止不动'),
    noTrim: true
  }
}

/**
 * 随机事件：从某个 loop 状态的 K0 出发、回到 K0，中间做一段别的动作。剧本按时间段写清楚。
 * 长度用 5 秒（124 帧）：试过 10 秒（243 帧），加了“单一镜头”的约束后不再切特写，但背景会从青色
 * 慢慢漂成灰色，画面也褪色，无法抠图；5 秒的片段从没出现过这个问题。
 * out 是 resources/assets/videos/loops/ 下的输出文件名。
 */
export const EVENT_FRAMES = 124
const ONE_SHOT = '剧本：'

const EVENTS = {
  'idle-yawn': {
    state: 'idle',
    k0: 'hub-A-approved',
    prompt:
      ONE_SHOT +
      '0到1秒，她安静地坐着自然呼吸；1到3秒，她有点困了，先抬起右手完全遮住嘴，然后在手后面打了一个小小的哈欠，眼睛眯起，肩膀微微耸起；' +
      '3到4秒，她放下手，眨眨眼恢复了精神；4到5秒，右手回到膝上合着的书上，回到最初的坐姿。嘴巴只在被手完全遮住时张开，其余时间始终闭合'
  },
  'idle-look': {
    state: 'idle',
    k0: 'hub-A-approved',
    prompt:
      ONE_SHOT +
      '0到1秒，她安静地坐着自然呼吸；1到2秒，她像是被什么吸引，转头望向画面右侧，好奇地歪了歪头；2到3秒，她又转头看向画面左侧，眨了眨眼；' +
      '转头的动作缓慢柔和，不要快速甩头；3到4秒，视线回到前方，抬起左手把耳边的一缕头发轻轻拢到耳后；4到5秒，左手回到膝上合着的书上，回到最初的坐姿。嘴巴始终闭合'
  },
  'thinking-tap': {
    state: 'thinking',
    k0: 'thinking',
    prompt:
      ONE_SHOT +
      '0到1秒，她指尖抵着下巴思考；1到3秒，她用指尖轻轻敲了几下下巴，头慢慢歪向一侧，眼睛望向上方，眉头微微皱起；' +
      '3到4秒，她像想到了什么，眼睛一亮，轻轻点了一下头；4到5秒，回到最初指尖抵着下巴的思考姿势。嘴巴始终闭合'
  },
  'reading-rub': {
    state: 'reading',
    k0: 'reading',
    prompt:
      ONE_SHOT +
      '0到1秒，她低头读着摊开的书；1到3秒，她抬起头，用一只手轻轻揉了揉眼睛，另一只手仍然按着书页；' +
      '3到4秒，她放下手，眨了眨眼；4到5秒，重新低头看向书页，回到最初的阅读姿势。书一直摊开不动，绝对不要翻页，嘴巴始终闭合'
  },
  'writing-review': {
    state: 'writing',
    k0: 'writing',
    prompt:
      ONE_SHOT +
      '0到1秒，她在书页上书写；1到3秒，她停下笔，把羽毛笔稍稍抬起，端详刚写好的字，满意地轻轻点了点头；' +
      '3到4秒，她把笔尖放回书页；4到5秒，继续书写，回到最初的姿势。书本不动，嘴巴始终闭合'
  },
  'confirmation-wave': {
    state: 'confirmation',
    k0: 'waiting-confirmation',
    prompt:
      ONE_SHOT +
      '0到1秒，她举着一只手望向观众等待；1到3秒，她把举起的手轻轻左右挥了挥，像在提醒观众，头微微歪向一侧；' +
      '3到4秒，手停下来，眨了眨眼；4到5秒，回到最初举手等待的姿势。嘴巴始终闭合'
  },
  'drowsy-jolt': {
    state: 'drowsy',
    k0: 'drowsy',
    prompt:
      ONE_SHOT +
      '0到1秒，她闭着眼打瞌睡；1到3秒，她的头慢慢越垂越低；3到4秒，头轻轻一顿，她像被惊醒一样微微睁开眼，眨了眨；' +
      '4到5秒，眼睛又慢慢闭上，头回到最初打盹的位置。手和书不动，嘴巴始终闭合'
  },
  'complete-sway': {
    state: 'complete',
    k0: 'complete',
    prompt:
      ONE_SHOT +
      '0到1秒，她把书抱在胸前坐着；1到3秒，她把书抱得更紧一些，身体轻轻地左右摇晃了两下；3到4秒，摇晃慢慢停下，眨了眨眼；' +
      '4到5秒，回到最初抱着书的坐姿。面部表情全程和第一帧一样，嘴唇一直闭合'
  },
  'thinking-ponder': {
    state: 'thinking',
    k0: 'thinking',
    prompt:
      ONE_SHOT +
      '0到1秒，她指尖抵着下巴思考；1到3秒，她抬起视线望向上方，另一只手的食指在空中轻轻画了两个小圈，像在心里计算；' +
      '3到4秒，手放下，视线慢慢回到前方；4到5秒，回到最初指尖抵着下巴的思考姿势。嘴巴始终闭合'
  },
  // 第二版：第一版 Q 版整个画面连书堆一起放大了，等于镜头推近
  'reading-lean': {
    state: 'reading',
    k0: 'reading',
    prompt:
      ONE_SHOT +
      '0到1秒，她低头读着摊开的书；1到3秒，她的上身微微前倾，低头凑近书页仔细看了看某一行，眉头轻轻皱起；' +
      '3到4秒，她舒展眉头，上身慢慢坐回；4到5秒，回到最初的阅读姿势。只有她的上身在动：人物大小、在画面中的位置和身下的书堆完全不变，镜头不推近、不放大。书一直摊开不动，绝对不要翻页，嘴巴始终闭合'
  },
  'writing-shake': {
    state: 'writing',
    k0: 'writing',
    prompt:
      ONE_SHOT +
      '0到1秒，她在书页上书写；1到3秒，她把羽毛笔抬离书页，在空中轻轻甩了两下，像在甩匀墨水，看了看笔尖；' +
      '3到4秒，她把笔尖放回书页；4到5秒，继续书写，回到最初的姿势。书本不动，嘴巴始终闭合'
  },
  'confirmation-lean': {
    state: 'confirmation',
    k0: 'waiting-confirmation',
    prompt:
      ONE_SHOT +
      '0到1秒，她举着一只手坐着等待；1到3秒，她的上身微微前倾，头歪向另一侧，举起的手轻轻晃了晃；' +
      '3到4秒，上身慢慢坐回；4到5秒，回到最初举手等待的姿势。面部表情全程和第一帧一样，嘴唇一直闭合'
  },
  'drowsy-sway': {
    state: 'drowsy',
    k0: 'drowsy',
    prompt:
      ONE_SHOT +
      '0到1秒，她闭着眼打瞌睡；1到3秒，她的身体随着缓慢的呼吸慢慢向一侧倾斜，像快要睡倒；3到4秒，她下意识地把身体扶正，眼睛仍然闭着；' +
      '4到5秒，回到最初打盹的姿势。手和书不动，嘴巴始终闭合'
  },
  'complete-lift': {
    state: 'complete',
    k0: 'complete',
    prompt:
      ONE_SHOT +
      '0到1秒，她把书抱在胸前坐着；1到3秒，她把书稍稍举起离开胸口，低头看了看书的封面；3到4秒，她把书慢慢抱回胸前；' +
      '4到5秒，回到最初抱着书的坐姿。面部表情全程和第一帧一样，嘴唇一直闭合'
  }
}

for (const [name, ev] of Object.entries(EVENTS)) {
  JOBS[`e-${name}`] = {
    state: ev.state,
    segment: `e-${name}`,
    first: ev.k0,
    last: ev.k0,
    frames: EVENT_FRAMES,
    prompt: ev.prompt,
    out: `claude-girl-event-${name}-transparent-9x16.webm`
  }
}

/**
 * 安静的底层 loop + 随机眨眼：循环感主要来自 loop 里固定节拍出现的显眼动作（每 5 秒准时眨一次眼、歪一次头）。
 * 底层 loop 只保留呼吸和极轻的起伏，不眨眼，头基本不动，看不出周期；眨眼做成约 1 秒的短事件，
 * 在 loop 之间随机插入（引擎按事件自己的概率和冷却决定）。
 */
const QUIET_FRAMES = 73 // 约 3 秒
const BLINK_FRAMES = 22 // 约 0.9 秒
const QUIET =
  '全程只有非常轻微的呼吸：胸口和肩膀极轻地起伏，身体几乎不动；眼睛一直睁着，不眨眼；头部保持不动；表情不变'

const QUIET_LOOPS = {
  idle: { k0: 'hub-A-approved', pose: '她安静地坐着，双手放在膝上合着的书上' },
  thinking: { k0: 'thinking', pose: '她指尖抵着下巴，保持思考的姿势' },
  reading: { k0: 'reading', pose: '她低头看着摊开的书，书和手完全不动，绝对不要翻页' },
  writing: { k0: 'writing', pose: '她握着羽毛笔停在书页上，笔和书都不动' },
  confirmation: { k0: 'waiting-confirmation', pose: '她举着一只手，歪着头，保持等待的姿势' },
  complete: { k0: 'complete', pose: '她把合起的书抱在胸前' },
  drowsy: { k0: 'drowsy', pose: '她闭着眼睛打瞌睡，眼睛始终闭着' }
}

/**
 * 持续摇晃的 loop（实验）：首尾帧相同时模型会“离开关键帧再回来”，两端速度趋近于零，循环感很强。
 * 改为两步：
 * 1. <状态>-M：关键帧锚在中间（第 MID_AT 帧），前后都是持续的动作，经过关键帧时不停下；
 * 2. <状态>-MB：用 M 靠后的一段和靠前的一段（各 22 帧）分别锚在开头和结尾，让模型生成中间的衔接，
 *    接缝两边都有真实的动作，速度能接上。
 * 然后用 assemble_loop.py 拼成从关键帧开始、又回到关键帧的一圈（任务 <状态>-ML），再交给 finish.py。
 */
export const MID_FRAMES = 124
export const MID_AT = 61
export const BRIDGE_FRAMES = 90
export const GUIDE_LEN = 22
export const LOOP_SPAN = 45 // 从 M 里取关键帧前后各多少帧
const SWAY =
  '身体像被微风吹着一样，持续、缓慢、平稳地左右轻轻摇晃，一直在动、没有停顿，节奏均匀；自然地呼吸，发丝随着摇晃轻轻飘动；头不抬也不低，眼睛一直睁着、不眨眼，表情平静，嘴巴闭合'
// 各状态持续的动作：都是一直在进行、没有起止的动作，不写“先……再回到……”
const SWAY_MOTION = {
  idle: { still: '双手和书保持不动', motion: SWAY },
  thinking: {
    still: '手指一直抵着下巴，手的位置不变；她身下坐着的书堆是静止的道具，完全不动、不变形、不滑动',
    motion: '身体持续、缓慢、平稳地左右轻轻摇晃，一直在动、没有停顿；视线若有所思地缓缓游移；自然地呼吸，发丝随着摇晃轻轻飘动；眼睛一直睁着、不眨眼，表情平静，嘴巴闭合'
  },
  reading: {
    still: '书和手完全不动，绝对不要翻页',
    motion: '她专注地看着书，身体随着呼吸持续、缓慢、平稳地轻轻摇晃，一直在动、没有停顿；视线在书页上缓缓移动；发丝轻轻飘动；眼睛一直睁着、不眨眼，表情平静，嘴巴闭合'
  },
  writing: {
    still: '书保持不动',
    motion: '她持续不断地用羽毛笔在书页上书写，笔尖一直在纸上移动、没有停顿；身体随着书写轻轻地晃动；发丝轻轻飘动；视线跟着笔尖；眼睛一直睁着、不眨眼，表情专注平静，嘴巴闭合'
  },
  confirmation: {
    still: '举起的手保持在原位',
    motion: '她耐心地等待着，身体持续、缓慢、平稳地左右轻轻摇晃，一直在动、没有停顿；自然地呼吸，发丝随着摇晃轻轻飘动；眼睛一直睁着、不眨眼，表情期待平静，嘴巴闭合'
  },
  complete: {
    still: '双手一直把书抱在胸前',
    motion: '她心情愉快，身体持续、轻快而平稳地左右轻轻摇晃，一直在动、没有停顿；自然地呼吸，发丝随着摇晃轻轻飘动；眼睛一直睁着、不眨眼，微笑平静，嘴巴闭合'
  },
  drowsy: {
    still: '双手保持不动',
    motion: '她闭着眼睛打瞌睡，头和身体随着缓慢深长的呼吸持续、缓慢、平稳地轻轻摇晃，一直在动、没有停顿；发丝轻轻飘动；眼睛始终闭着，表情安详，嘴巴闭合'
  }
}
// 枢纽 B 上没有状态，这段 loop 不播放，只给经过枢纽 B 的过渡做引导（让它们在 B 上带着动作衔接）
SWAY_MOTION.hubB = {
  still: '书一直摊开在膝上，双手扶着书，绝对不要翻页',
  motion: '身体持续、缓慢、平稳地左右轻轻摇晃，一直在动、没有停顿；自然地呼吸，发丝随着摇晃轻轻飘动；眼睛一直睁着、不眨眼，表情平静，嘴巴闭合'
}
const SWAY_LOOPS = Object.fromEntries(
  Object.keys(SWAY_MOTION).map(s => [s, s === 'hubB' ? { k0: 'hub-B-approved', pose: '她坐着，双手捧着摊开在膝上的书' } : QUIET_LOOPS[s]])
)
for (const [state, q] of Object.entries(SWAY_LOOPS)) {
  const prompt = `${q.pose}，${SWAY_MOTION[state].still}。${SWAY_MOTION[state].motion}`
  JOBS[`${state}-M`] = { state, segment: 'M', frames: MID_FRAMES, guides: [{ image: q.k0, at: MID_AT }], prompt, noTrim: true }
  JOBS[`${state}-MB`] = {
    state,
    segment: 'MB',
    frames: BRIDGE_FRAMES,
    guides: [
      { from: `${state}-M`, start: MID_AT + LOOP_SPAN - GUIDE_LEN + 1, count: GUIDE_LEN, at: 0 },
      { from: `${state}-M`, start: MID_AT - LOOP_SPAN, count: GUIDE_LEN, at: -GUIDE_LEN }
    ],
    prompt,
    noTrim: true
  }
}

/**
 * 摇晃 loop 的眨眼版本：不能把眨眼做成单独的事件（事件从静止的关键帧开始，眨眼时摇晃会停下）。
 * 改为在拼好的 loop（<状态>-ML）里挑一段，前后各 GUIDE_LEN 帧用原 loop 的帧锚住，只重新生成中间约 1.2 秒，
 * 让她在摇晃中眨一次眼。assemble_loop.py blink 把它拼回去，得到和原 loop 首尾相同的变体，引擎每轮随机挑一段。
 */
export const BLINK_VARIANT_FRAMES = 73
export const BLINK_VARIANTS = { 2: 10, 3: 60 } // 变体编号: 在 ML 里从第几帧开始重新生成
for (const [state, q] of Object.entries(SWAY_LOOPS)) {
  if (state === 'drowsy' || state === 'hubB') continue // drowsy 一直闭着眼；枢纽 B 的 loop 不播放
  for (const [n, start] of Object.entries(BLINK_VARIANTS)) {
    JOBS[`${state}-MK${n}`] = {
      state,
      segment: `MK${n}`,
      frames: BLINK_VARIANT_FRAMES,
      guides: [
        { from: `${state}-ML`, start, count: GUIDE_LEN, at: 0 },
        { from: `${state}-ML`, start: start + BLINK_VARIANT_FRAMES - GUIDE_LEN, count: GUIDE_LEN, at: -GUIDE_LEN }
      ],
      prompt: `${q.pose}，${SWAY_MOTION[state].still}。${SWAY_MOTION[state].motion.replace('眼睛一直睁着、不眨眼', '中途自然地眨一次眼，眨完眼睛睁开')}`,
      noTrim: true
    }
  }
}

/**
 * 切换形象的变身动画（任务名 S-to-chibi / S-to-adult，在原版环境下生成）：两端分别用两个形象 idle loop 的帧锚住，
 * 所以变身前后都带着摇晃接上。Q 版的帧从 Q 版的生成目录读（../claude-girl-gen-chibi/）。
 * finish 之前要把 Q 版 idle 的标准帧复制到原版的 _canonical/chibi-hub-A-approved.png，两边的端点才完全一致。
 */
if (!SKIN) {
  // 特效要小：大团烟雾和闪光会盖住背景、碰到画面边缘，抠不了图（背景漂移检测连续失败）
  const MAGIC =
    '她身边冒出一圈小小的闪亮星星和光点，光点只在她身体周围、离画面边缘很远，背景始终是纯青色、不变亮也不变色；在光点中她的身形慢慢变化，光点消失后'
  JOBS['S-to-chibi'] = {
    transition: 'switch-to-chibi',
    first: 'hub-A-approved',
    last: 'chibi-hub-A-approved',
    frames: 124,
    guides: [
      { from: 'idle-ML', start: 0, count: 22, at: 0 },
      { from: '../claude-girl-gen-chibi/idle-ML', start: -22, count: 22, at: -22 }
    ],
    prompt: `开头她还在轻轻摇晃，接着${MAGIC}，她变成了Q版三头身的小小的自己，还是坐在同样的书堆上，表情冷淡，最后轻轻摇晃`,
    noTrim: true
  }
  JOBS['S-to-adult'] = {
    transition: 'switch-to-adult',
    first: 'chibi-hub-A-approved',
    last: 'hub-A-approved',
    frames: 124,
    guides: [
      { from: '../claude-girl-gen-chibi/idle-ML', start: 0, count: 22, at: 0 },
      { from: 'idle-ML', start: -22, count: 22, at: -22 }
    ],
    prompt: `开头Q版的她还在轻轻摇晃，接着${MAGIC}，她变回了原本成熟的大人模样，还是坐在同样的书堆上，表情平静，最后轻轻摇晃`,
    noTrim: true
  }
}

/**
 * 插入式随机动作（任务名 E-<事件名>）：不再从静止的关键帧开始，而是插在摇晃 loop 的某一帧（at）后面。
 * 开头 22 帧锚住 loop 里第 at-21 到 at 帧，结尾 22 帧锚住第 at+1 到 at+22 帧，中间约 4.75 秒生成动作：
 * 模型从“摇晃到第 at 帧的样子”开始，做完动作回到“摇晃到第 at+1 帧的样子”。
 * assemble_loop.py --insert 把它插回 loop，得到“摇一会儿 → 做动作 → 接着摇”的一整段，首尾仍是关键帧，
 * 作为 event 登记（按概率和冷却插播），摇晃全程不停。
 */
export const INSERT_FRAMES = 158
const INSERTS = {
  'idle-yawn': 40,
  'idle-look': 90,
  'thinking-tap': 40,
  'thinking-ponder': 90,
  'reading-rub': 40,
  'reading-lean': 90,
  'writing-review': 40,
  'writing-shake': 90,
  'confirmation-wave': 40,
  'confirmation-lean': 90,
  'drowsy-jolt': 60,
  'complete-lift': 60,
  'waiting-watch': 40,
  // 第二批（2026-10）：符合稳重性格的安静小动作；道具一律“从无到有再到无”（借鉴 dsh-pet）
  'idle-tea': 30,
  'idle-flower': 70,
  'idle-pages': 100,
  'idle-stretch': 30,
  'idle-rest': 70,
  'idle-gaze': 100,
  'thinking-bulb': 70,
  'reading-page': 70,
  'writing-ink': 70,
  'confirmation-tap2': 70,
  'complete-hum': 30,
  'drowsy-bubble': 90
}
// 道具凭空出现、再消散：起止帧都没有道具，衔接回 loop 时画面干净
const MAGIC_PROP = '道具一律从无到有：先出现淡淡的光点和半透明的虚影，约半秒后凝聚成实体；用完后再化成光点慢慢消散，不会凭空直接出现或消失'
Object.assign(EVENTS, {
  // 第二版：第一版杯子比脸还大、像端碗、整张脸被挡住 1.5 秒、变出来时把人照亮、热气糊成一团
  'idle-tea': { state: 'idle', prompt: ONE_SHOT +
    '0到1秒，她安静地坐着；1到2秒，她右手边出现几颗很淡的小光点，凝聚成一只小巧的白瓷茶杯——茶杯只有她手掌那么大，比她的脸小得多；' +
    '她用右手拇指和食指优雅地捏住杯柄；2到3.5秒，她把茶杯送到唇边，轻轻抿了一小口，杯子只挡住下巴，眼睛和鼻子始终露在外面，神情满足；' +
    '3.5到4.5秒，她放下茶杯，茶杯化作几颗淡淡的光点消散，右手回到膝上的书上。光点很弱、只在茶杯周围，不照亮她的身体，背景颜色不变；茶杯上没有热气。嘴唇贴着杯沿时不张大嘴' },
  'idle-flower': { state: 'idle', prompt: ONE_SHOT +
    '0到1秒，她安静地坐着；1到3秒，她抬起左手，轻轻扶正头上的橙色花饰，顺手把耳边的一缕头发拢到耳后；' +
    '3到4.5秒，手慢慢放回膝上的书上，回到最初的坐姿。嘴巴始终闭合' },
  'idle-pages': { state: 'idle', prompt: ONE_SHOT +
    '0到1秒，她安静地坐着；1到2秒，她把膝上合着的书轻轻打开；2到3.5秒，她低头看着书页，用指尖慢慢翻过两页；' +
    '3.5到4.5秒，她把书轻轻合上，双手放回书上，回到最初的坐姿。嘴巴始终闭合' },
  // 第二版：第一版原版变成了双手合十像祈祷、手还半透明；照 Q 版成功的样子写清手臂的位置
  'idle-stretch': { state: 'idle', prompt: ONE_SHOT +
    '0到1秒，她安静地坐着；1到2.5秒，她双手手指在头顶上方交扣，掌心朝上，手臂向上伸直，舒服地伸了一个懒腰，眼睛眯起，身体微微后仰；' +
    '2.5到4.5秒，她慢慢放下双手，回到膝上的书上，回到最初的坐姿。双手始终清晰完整，动作优雅，嘴巴始终闭合' },
  'idle-rest': { state: 'idle', prompt: ONE_SHOT +
    '0到1秒，她安静地坐着；1到1.5秒，她慢慢闭上眼睛；1.5到3.5秒，她闭着眼睛安静地养神，神情放松；' +
    '3.5到4.5秒，她慢慢睁开眼睛，琥珀色的眼睛重新看向前方。嘴巴始终闭合' },
  'idle-gaze': { state: 'idle', prompt: ONE_SHOT +
    '0到1秒，她安静地坐着；1到3.5秒，她的视线慢慢移向远处，像在望着窗外出神，嘴角浮起一丝淡淡的微笑；' +
    '3.5到4.5秒，视线慢慢回到前方，回到最初的神情。头部只有很小的转动，嘴巴始终闭合' },
  'thinking-bulb': { state: 'thinking', prompt: ONE_SHOT +
    '0到1.5秒，她指尖抵着下巴思考；1.5到3秒，她头顶上方的光点凝聚成一个小小的卡通灯泡（灯泡本身是亮的，但不向周围发光、没有光晕，背景和她身上的光照完全不变），她的眼睛微微一亮；' +
    '3到4.5秒，灯泡化作光点慢慢消散，她回到指尖抵着下巴的思考姿势。' + MAGIC_PROP + '，嘴巴始终闭合' },
  'reading-page': { state: 'reading', prompt: ONE_SHOT +
    '0到1.5秒，她低头读着摊开的书；1.5到3秒，她用右手指尖捏住书页的一角，小心地翻过一页；' +
    '3到4.5秒，她把手放回书边，继续低头阅读新的一页，回到最初的阅读姿势。书本不移动，嘴巴始终闭合' },
  'writing-ink': { state: 'writing', prompt: ONE_SHOT +
    '0到1秒，她在书页上书写；1到2秒，书页旁边的光点凝聚成一只小小的墨水瓶；2到3秒，她把羽毛笔尖轻轻在墨水瓶里蘸一下；' +
    '3到4.5秒，墨水瓶化作光点慢慢消散，她把笔尖放回书页继续书写。' + MAGIC_PROP + '，书本不动，嘴巴始终闭合' },
  'confirmation-tap2': { state: 'confirmation', prompt: ONE_SHOT +
    '0到1秒，她举着一只手等待；1到3秒，她用举起那只手的食指在空中轻轻点了两下，像在敲一块看不见的屏幕提醒对方；' +
    '3到4.5秒，她回到最初举手等待的姿势。嘴巴始终闭合' },
  // 第二版：第一版 Q 版嘴一开一合像在唱歌说话；改成只用头部的节奏表现愉快
  'complete-hum': { state: 'complete', prompt: ONE_SHOT +
    '0到1秒，她把书抱在胸前坐着；1到3.5秒，她闭上眼睛，心情愉快，头随着心里的节奏轻轻左右摆了两下，嘴角微微上扬；' +
    '3.5到4.5秒，她睁开眼睛，回到最初抱着书的坐姿。嘴唇始终紧紧闭合成一条线，完全不张嘴，不出声，不唱歌' },
  'drowsy-bubble': { state: 'drowsy', prompt: ONE_SHOT +
    '0到1秒，她闭着眼打瞌睡；1到3秒，她头顶上方慢慢飘出一个小小的透明“Zzz”泡泡，缓缓上升；' +
    '3到4.5秒，泡泡轻轻破掉，化作光点消散，她继续安静地打瞌睡。眼睛始终闭着，手和书不动，嘴巴始终闭合' }
})

// 动作多的插入式动作生成得长一些（中间的动作时长 = 帧数 - 44）
// Q 版 192 帧连续失败（中段背景加了暗角、变成灰蓝色），缩短到 158
const INSERT_LENGTH = { 'waiting-watch': SKIN === 'chibi' ? 158 : 192 }
// waiting 看起来就是 idle，只是时不时拿出怀表看时间：插在 idle 的 loop 里，怀表的样子参照 Qwen Image 编辑出的图
EVENTS['waiting-watch'] = {
  state: 'idle',
  k0: 'hub-A-approved',
  // 参考图是原版的怀表图：Q 版用它会被拉向原版的构图（连续三次切镜头），Q 版只用文字描述
  refs: SKIN === 'chibi' ? undefined : ['pocket-watch-ref'],
  prompt:
    ONE_SHOT +
    `0到1秒，她安静地坐着自然呼吸；1到2秒，她从腰间取出一只带表盖的金色怀表${SKIN === 'chibi' ? '' : '（样子参照<Picture 1>里的怀表）'}，拿在胸前；` +
    '2到4秒，她用拇指打开表盖，低头看了看表盘上的时间，神情平静；4到5秒，她合上表盖，把怀表放回腰间；' +
    '5到6秒，双手回到膝上合着的书上，回到最初的坐姿。膝上的书和身下的书堆一直不动，嘴巴始终闭合' +
    (SKIN === 'chibi' ? '。背景全程是均匀的纯青色，没有暗角、没有渐变、没有光影变化' : '')
}
for (const [name, at] of Object.entries(INSERTS)) {
  const e = EVENTS[name]
  JOBS[`E-${name}`] = {
    state: e.state,
    segment: `E-${name}`,
    event: name,
    insertAt: at,
    frames: INSERT_LENGTH[name] ?? INSERT_FRAMES,
    guides: [
      { from: `${e.state}-ML`, start: at - GUIDE_LEN + 1, count: GUIDE_LEN, at: 0 },
      { from: `${e.state}-ML`, start: at + 1, count: GUIDE_LEN, at: -GUIDE_LEN }
    ],
    // drowsy 的 loop 一直闭着眼，锚定的帧里看不到瞳色，惊醒时模型会睁出蓝眼睛；写明瞳色（只给会睁眼的惊醒，别的 drowsy 动作全程闭眼）
    prompt:
      `${SWAY_LOOPS[e.state].pose}。开头和结尾她都和前后一样持续轻轻摇晃，中间做一段动作，动作自然从容——${e.prompt.replace(ONE_SHOT, '')}` +
      (name === 'drowsy-jolt'
        ? '。她睁眼时只是迷迷糊糊地微微睁开一条缝，露出的瞳孔是琥珀色（橙金色，和头发颜色相近），和<Picture 1>里她睁着的眼睛一样，绝对不是蓝色或灰色'
        : ''),
    refs: e.refs ?? (name === 'drowsy-jolt' ? ['hub-A-approved'] : undefined),
    noTrim: true
  }
}

for (const [state, q] of Object.entries(QUIET_LOOPS)) {
  const quiet = state === 'drowsy' ? QUIET.replace('眼睛一直睁着，不眨眼；', '') : QUIET
  JOBS[`${state}-Q`] = {
    state,
    segment: 'Q',
    first: q.k0,
    last: q.k0,
    frames: QUIET_FRAMES,
    prompt: `${q.pose}。${quiet}`,
    noTrim: true, // 整段都近乎静止，不能按“首尾静止帧”去剪
    out: `claude-girl-loop-${state}-quiet-transparent-9x16.webm`
  }
  const blink =
    state === 'drowsy'
      ? { frames: 39, prompt: `${q.pose}。她的头很轻地往下一点，又慢慢回到原位，眼睛始终闭着，身体不动` }
      : { frames: BLINK_FRAMES, prompt: `${q.pose}。她自然地眨一次眼，除了眼睛以外全身都不动，表情不变` }
  JOBS[`b-${state}`] = {
    state,
    segment: `b-${state}`,
    first: q.k0,
    last: q.k0,
    ...blink,
    noTrim: true,
    out: `claude-girl-event-${state}-blink-transparent-9x16.webm`
  }
}
