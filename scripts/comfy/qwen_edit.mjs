#!/usr/bin/env node
// 用 Qwen Image 2.1 编辑关键帧（按官方 image_qwen_image_2_1_image_edit 模板：25 步、CFG 1、euler / simple）。
//
//   node scripts/comfy/qwen_edit.mjs <任务名>          # 任务定义见下面的 EDITS
//   node scripts/comfy/qwen_edit.mjs <任务名> --count 4  # 换种子出几张候选
//
// 参考图用 ComfyUI input 目录里的青色关键帧（claude-girl-<名字>-cyan-9x16.png），第一张决定画布大小，
// 所以出图直接是同样构图、同样青色背景的 1024×1824，可以直接接视频流程。
// 输出在 ComfyUI/output/claude-girl-kf/<任务名>/。

const COMFY = process.env.COMFY_URL ?? 'http://127.0.0.1:8188'
const args = process.argv.slice(2)
const name = args.find(a => !a.startsWith('--'))
const count = args.includes('--count') ? Number(args[args.indexOf('--count') + 1]) || 1 : 1

const KEEP =
  '保持<image1>中的角色完全不变：同一个人、同样的脸、发型、发色、琥珀色的眼睛、服装和配饰、画风和线条；' +
  '人物的大小、位置和构图不变，仍然坐在同样的书堆上，纯青色背景不变。'
const NEGATIVE = '多余的手指，畸形的手，变形，模糊，文字，水印，边框，背景变化，人物变大或变小，张嘴说话'

const EDITS = {
  // Q 版（chibi）：同一个角色，只改头身比。背景、坐姿、书和书堆都保留
  ...Object.fromEntries(
    [
      ['chibi-2', '二头身'],
      ['chibi-2.5', '二头半身'],
      ['chibi-3', '三头身']
    ].map(([key, ratio]) => [
      key,
      {
        refs: ['hub-A-approved'],
        prompt:
          `把<image1>中的角色画成可爱的Q版（chibi）${ratio}比例：头很大、身体小而圆润、手脚短小，大眼睛，线条干净，二次元Q版风格。` +
          '保持角色的所有特征：橙色的长发和发型、头上的橙色花饰和黑色蝴蝶结、琥珀色的眼睛、白色衬衫和黑色胸前领结、黑色束腰、白色长裙和橙黑色的裙摆装饰、白色系带短靴。' +
          '保持同样的姿势：安静地坐在同样的一叠书上，双手放在膝上一本合着的书上，表情平静、带一点微笑，嘴巴闭合。' +
          '人物完整地在画面正中，占画面高度的大约三分之二，纯青色背景不变。'
      }
    ])
  ),
  // waiting：Claude 在等后台任务，不需要用户操作。悠闲、耐心地等
  // 用户选了三头身，但要比大人版开朗：笑容更灿烂、有活力
  'chibi-3-bright': {
    refs: ['hub-A-approved'],
    prompt:
      '把<image1>中的角色画成可爱的Q版（chibi）三头身比例：头大、身体小而圆润、手脚短小，大眼睛，线条干净，二次元Q版风格。' +
      '性格比原图开朗活泼得多：灿烂开心的笑容，可以微微张嘴笑，眼睛明亮有神、带着笑意，脸颊微微泛红，头稍稍歪向一侧，整个人看起来元气满满、很有活力。' +
      '保持角色的所有特征：橙色的长发和发型、头上的橙色花饰和黑色蝴蝶结、琥珀色的眼睛、白色衬衫和黑色胸前领结、黑色束腰、白色长裙和橙黑色的裙摆装饰、白色系带短靴。' +
      '保持同样的姿势：坐在同样的一叠书上，双手放在膝上一本合着的书上。' +
      '人物完整地在画面正中，占画面高度的大约三分之二，纯青色背景不变。'
  },
  // 最终方向：冷脸萌。Q 版三头身，但保留大小姐的气场：淡定、面无表情，反差萌
  'chibi-3-cool': {
    refs: ['hub-A-approved'],
    prompt:
      '把<image1>中的角色画成可爱的Q版（chibi）三头身比例：头大、身体小而圆润、手脚短小，大眼睛，线条干净，二次元Q版风格。' +
      '表情是冷脸萌：面无表情、淡定高冷，眼睛微微半垂、目光平静，嘴巴闭成一条小小的直线，没有笑容，带着大小姐般的威严和气场；' +
      '圆滚滚的Q版身体配上一本正经的冷淡表情，形成反差萌。坐姿端正优雅。' +
      '保持角色的所有特征：橙色的长发和发型、头上的橙色花饰和黑色蝴蝶结、琥珀色的眼睛、白色衬衫和黑色胸前领结、黑色束腰、白色长裙和橙黑色的裙摆装饰、白色系带短靴。' +
      '保持同样的姿势：坐在同样的一叠书上，双手放在膝上一本合着的书上。' +
      '人物完整地在画面正中，占画面高度的大约三分之二，纯青色背景不变。'
  },
  'waiting-watch': {
    refs: ['hub-A-approved'],
    prompt: `${KEEP}只改变她的姿势和手里的东西：她双手捧着一只小巧的金色怀表放在膝上，低头悠闲地看着表盘，表情平静放松、带一点微笑，像在耐心地等待。原来膝上的书放在身旁的书堆上。嘴巴闭合。`
  },
  // 用户更喜欢怀表，但要保留书堆和膝上的书（第一版怀表把书挪走了、书堆多了一本）
  'waiting-watch2': {
    refs: ['hub-A-approved'],
    prompt: `${KEEP}身下的书堆和<image1>完全一样，书的数量、摆放和颜色都不变，不要增加或移动任何书；膝上那本合着的书也保持原样放在膝上。只改变她的双手：她双手捧着一只金色怀表，放在膝上那本合着的书上，表盖打开，表盘清晰可见，怀表稍大一些、容易看清；她低头悠闲地看着表盘，表情平静放松、带一点微笑，像在耐心地等待。嘴巴闭合。`
  },
  'waiting-hourglass': {
    refs: ['hub-A-approved'],
    prompt: `${KEEP}只改变她的姿势和手里的东西：她双手轻轻托着一个小沙漏放在膝上合着的书上，沙子正在缓缓流下，她低头安静地看着沙漏，表情平静放松、带一点微笑，像在耐心地等待。嘴巴闭合。`
  }
}

// Q 版各状态的关键帧：只用定稿的 Q 版 idle 做参考（比例、画风、表情、大小位置、书堆、背景都以它为准），
// 姿势用文字写清楚——同时给原版关键帧做参考时，模型不照搬姿势，反而把人物大小和位置改了。
// error 不照原版，做成 Q 版专属的抱头蹲防。
const CHIBI_KEEP =
  '其余全部保持<image1>不变：Q版三头身的比例和画风、面无表情的冷淡神情（冷脸萌，有大小姐的气场）、琥珀色的眼睛、发型和服装、' +
  '人物的大小和在画面中的位置必须和<image1>完全一致、身下同样的书堆、纯青色背景。只画一个角色，嘴巴闭合。'
const CHIBI_POSES = {
  'hub-B-approved': '她双手捧着一本摊开的书放在膝上，书页朝上，视线平静地看向前方。',
  thinking: '她抬起右手，食指轻轻抵住下巴，视线望向斜上方，陷入思考；左手放在膝上合着的书上。',
  reading: '她双手捧着膝上一本摊开的书，低头专注地看着书页。',
  writing: '膝上的书摊开平放，她右手握着一支白色的羽毛笔在书页上写字，左手按着书页，低头看着笔尖。',
  'waiting-confirmation': '她抬起右手，掌心朝向观众，头微微歪向一侧，看着观众，像在询问“可以吗”；左手放在膝上合着的书上。',
  complete: '她双手把合起的书抱在胸前，神情里带一点点克制的得意，但依然冷淡。',
  drowsy: '她闭着眼睛打瞌睡，头轻轻歪向一侧，双手放在膝上合着的书上。'
}
for (const [key, pose] of Object.entries(CHIBI_POSES)) {
  EDITS[`chibi-${key}`] = {
    refs: ['chibi-hub-A-approved'],
    prompt: `把<image1>里的Q版角色改成这个姿势：${pose}${CHIBI_KEEP}`
  }
}
// 抱头蹲防：只动上身，脚照常垂着（收起膝盖的话腿会挡住书堆，书堆也跟着变，和别的关键帧对不齐）
EDITS['chibi-error'] = {
  refs: ['chibi-hub-A-approved'],
  prompt:
    '把<image1>里的Q版角色改成“抱头蹲防”的样子：她被吓了一跳，双手紧紧抱住脑袋，缩着脖子、上身往前蜷起来，' +
    '眼睛紧紧闭着，表情委屈又慌张，额头冒出一滴冷汗；膝上的书还在膝上。' +
    '腰部以下完全保持<image1>不变：仍然坐在同一个位置，双腿和靴子的位置不变，身下的书堆和<image1>完全相同（书的数量、大小、位置都不变）。' +
    '其余全部保持<image1>：Q版三头身的比例和画风、琥珀色的眼睛、发型和服装、人物的大小和位置、纯青色背景。只画一个角色。'
}

// 第二版：第一版双臂交叉挡脸、耳边又多出一只手，视频里看着像三只手。改成两只手都放在头顶、手肘向两侧张开，脸露出来
EDITS['chibi-error2'] = {
  refs: ['chibi-hub-A-approved'],
  prompt:
    '把<image1>里的Q版角色改成“抱头蹲防”的样子：她被吓了一跳，两只手一左一右按在自己头顶上捂住脑袋，两边手肘向外张开，' +
    '缩着脖子、上身微微往前蜷；脸完全露出来、不被手臂挡住，眼睛紧紧闭着，表情委屈又慌张，额头冒出一滴冷汗；膝上的书还在膝上。' +
    '画面里一共只有两只手，都在头顶，手臂不交叉。' +
    '腰部以下完全保持<image1>不变：仍然坐在同一个位置，双腿和靴子的位置不变，身下的书堆和<image1>完全相同（书的数量、大小、位置都不变）。' +
    '其余全部保持<image1>：Q版三头身的比例和画风、琥珀色的眼睛、发型和服装、人物的大小和位置、纯青色背景。只画一个角色。'
}

// 换装形象（只用原版的人）：同一个人、同样的脸和琥珀色的眼睛，坐姿、书堆、构图不变，只换衣服、发型和气质
const OUTFIT_KEEP =
  '保持<image1>中的角色本人不变：同一张脸、橙色的长发发色、琥珀色的眼睛、画风和线条；' +
  '保持同样的坐姿：坐在同样的一叠书上，双手放在膝上一本合着的书上；人物的大小、位置和构图不变，纯青色背景不变。只画一个角色，嘴巴闭合。'
EDITS['outfit-maid'] = {
  refs: ['hub-A-approved'],
  prompt:
    '把<image1>中的角色换成经典女仆装：黑色长袖连衣裙，白色荷叶边围裙，头上戴白色荷叶边女仆头饰，领口有小小的黑色蝴蝶结，' +
    `白色长袜，黑色玛丽珍鞋；头发保持长直发，可以保留头上的橙色花饰；表情平静端庄。${OUTFIT_KEEP}`
}
EDITS['outfit-lively-school'] = {
  refs: ['hub-A-approved'],
  prompt:
    '把<image1>中的角色换成更活泼的学院风形象：短款的深蓝色西装外套配白衬衫和红色领结，橙色格子短裙，黑色过膝袜，棕色乐福鞋；' +
    `头发扎成高高的马尾，用橙色发圈；表情活泼开朗，灿烂的笑容，眼睛弯弯的（嘴巴闭着微笑）。${OUTFIT_KEEP}`
}
EDITS['outfit-lively-casual'] = {
  refs: ['hub-A-approved'],
  prompt:
    '把<image1>中的角色换成活泼的休闲装：宽松的白色连帽卫衣，袖子有点长盖住半个手，橙色短裤，白色高帮运动鞋，一只脚的袜子是橙色条纹；' +
    `头发随性地扎成低双马尾；表情俏皮活泼，歪头眨一只眼（嘴巴闭着微笑）。${OUTFIT_KEEP}`
}

// 精灵风格：保留克劳德酱原本的服装和配饰，只加精灵元素（第一版整套换成了精灵长裙，用户不要）
EDITS['outfit-elf'] = {
  refs: ['hub-A-approved'],
  prompt:
    '保持<image1>中角色原本的全部造型不变：白色衬衫和荷叶边领口、黑色领结、黑色束腰、白色长裙和橙黑色的裙摆装饰、头上的橙色花饰和黑色蝴蝶结、白色系带短靴。' +
    '在这个基础上加入精灵风格：尖尖的精灵耳朵从头发里露出来，裙摆和袖口多了淡金色的叶子与藤蔓刺绣，橙色花饰旁边点缀几片小小的绿叶，' +
    `整体气质更空灵、优雅一些，像森林里的精灵大姐姐。${OUTFIT_KEEP}`
}

// 第二版：在克劳德酱原本的设计上换主题（发型、橙色花饰、黑色蝴蝶结、束腰、橙黑白配色、裙摆刺绣都保留），
// 第一版整套换掉了衣服，偏离太多。女仆装照用户给的设计图（maid-example）。
const CLAUDE_KEEP =
  '保留克劳德酱的标志性设计：橙色长发、头上的橙色花饰和黑色蝴蝶结、黑色束腰、白衬衫和黑色领结、橙黑白三色的配色、裙摆上的橙色刺绣和层叠荷叶边。'
EDITS['outfit-maid2'] = {
  refs: ['hub-A-approved', 'maid-example'],
  prompt:
    '<image1>是角色原本的样子，<image2>是她的女仆装设计。把<image1>里的角色换成<image2>这套女仆装：白色荷叶边女仆头饰、' +
    '黑色蓬袖连衣裙、白色长围裙、胸前的黑色大蝴蝶结、黑色束腰、橙黑白配色和裙摆的橙色刺绣，脚上是白色系带短靴。' +
    `表情平静端庄。不要照搬<image2>的站姿，${OUTFIT_KEEP}`
}
// 女仆形象（第三个形象）：用户给的高清设计图（maid-ref，1052×1870，和 maid-example 是同一套设计）
EDITS['maid-hub-A'] = {
  refs: ['hub-A-approved', 'maid-ref'],
  prompt:
    '<image1>是角色原本的样子，<image2>是她的女仆装设计。把<image1>里的角色换成<image2>这套女仆装，细节照<image2>：' +
    '头上的白色荷叶边女仆头饰，右侧的橙色花饰和黑色蝴蝶结、白色飘带和流苏；高高的白色荷叶边立领，胸前黑色大蝴蝶结配橙色花朵胸针；' +
    '白色衬衫前襟带一排小扣子和荷叶边；黑色蓬袖长袖，袖子上有橙色花朵刺绣，白色荷叶边袖口系黑色细带；带金色扣子的黑色束腰；' +
    '长长的白色围裙，边缘是荷叶边和橙色藤蔓刺绣；黑色长裙，裙摆有金边和橙色花纹刺绣，里层露出橙色衬裙；' +
    '右侧腰间垂着橙黑两色的长飘带、黑色蝴蝶结和橙色流苏；白色系带高跟短靴。表情平静端庄、有点冷淡。' +
    `不要照搬<image2>的站姿和提裙子的动作，${OUTFIT_KEEP}`
}
// 女仆形象的其余关键帧：只用定稿的女仆 idle（maid-hub-A-approved）做参考，姿势用文字写清。error 照原版（吃了一惊把书抱到胸前）
const MAID_KEEP =
  '其余全部保持<image1>不变：女仆装的全部细节（头饰、蝴蝶结、围裙、袖子刺绣、腰间飘带和流苏）、发型和发饰、琥珀色的眼睛、平静偏冷的神情、画风、' +
  '人物的大小和在画面中的位置必须和<image1>完全一致、身下同样的书堆、纯青色背景。只画一个角色，嘴巴闭合。'
const MAID_POSES = {
  ...CHIBI_POSES,
  complete: '她双手把合起的书抱在胸前，神情满足，带着淡淡的微笑。',
  error: '她吃了一惊，慌张地把膝上的书举到胸前紧紧抱住，眉头微皱，表情有些不知所措。'
}
for (const [key, pose] of Object.entries(MAID_POSES)) {
  EDITS[`maid-${key}`] = {
    refs: ['maid-hub-A-approved'],
    prompt: `把<image1>里的女仆装角色改成这个姿势：${pose}${MAID_KEEP}`
  }
}

// 第二版：第一版写字、读书时都抬眼盯着观众。把视线写死：低头、看书页，不看观众
const LOOK_DOWN = '她的头微微低下，眼睛向下看，视线完全落在书页上，绝对不看向观众、不看镜头。'
EDITS['maid-writing2'] = {
  refs: ['maid-hub-A-approved'],
  prompt: `把<image1>里的女仆装角色改成这个姿势：膝上的书摊开平放，她右手握着一支白色的羽毛笔在书页上写字，左手按着书页，${LOOK_DOWN}${MAID_KEEP}`
}
EDITS['maid-reading2'] = {
  refs: ['maid-hub-A-approved'],
  prompt: `把<image1>里的女仆装角色改成这个姿势：她双手捧着膝上一本摊开的书，专注地阅读，${LOOK_DOWN}${MAID_KEEP}`
}

EDITS['outfit-lively2'] = {
  refs: ['hub-A-approved'],
  prompt:
    `把<image1>中的角色改成更活泼的版本。${CLAUDE_KEEP}` +
    '改动：橙色长发扎成高高的马尾，花饰和蝴蝶结戴在马尾根部；长裙改成到膝盖上方的蓬蓬短裙，层层荷叶边更蓬松；' +
    '长袖改成短短的泡泡袖，配白色短手套；白色及膝袜和白色系带短靴；表情活泼开朗、带着灿烂的笑容（嘴巴闭着微笑），眼睛明亮。' +
    `${OUTFIT_KEEP}`
}

const edit = EDITS[name]
if (!edit) {
  console.log(`没有这个任务：${name}\n可用：${Object.keys(EDITS).join('、')}`)
  process.exit(1)
}

const prompt = {
  unet: { class_type: 'UNETLoader', inputs: { unet_name: 'qwen_image_2.1_int8_convrot.safetensors', weight_dtype: 'default' } },
  cache: { class_type: 'QwenImage21Cache', inputs: { model: ['unet', 0], device: 'auto', dtype: 'default' } },
  clip: { class_type: 'CLIPLoader', inputs: { clip_name: 'qwen3vl_8b_int8_convrot.safetensors', type: 'qwen_image', device: 'default' } },
  vae: { class_type: 'VAELoader', inputs: { vae_name: 'qwen_image_2.1_vae_bf16.safetensors' } },
  encode: {
    class_type: 'TextEncodeQwenImage21',
    inputs: { clip: ['clip', 0], vae: ['vae', 0], prompt: edit.prompt, negative_prompt: NEGATIVE, resolution: 0 }
  },
  sample: {
    class_type: 'KSampler',
    inputs: {
      model: ['cache', 0], positive: ['encode', 0], negative: ['encode', 1], latent_image: ['encode', 2],
      seed: 0, steps: 25, cfg: 1, sampler_name: 'euler', scheduler: 'simple', denoise: 1
    }
  },
  decode: { class_type: 'VAEDecode', inputs: { samples: ['sample', 0], vae: ['vae', 0] } },
  save: { class_type: 'SaveImage', inputs: { images: ['decode', 0], filename_prefix: `claude-girl-kf/${name}/cand` } }
}
for (const [i, r] of edit.refs.entries()) {
  prompt[`ref${i}`] = { class_type: 'LoadImage', inputs: { image: `claude-girl-${r}-cyan-9x16.png` } }
  prompt.encode.inputs[`images.image_${i + 1}`] = [`ref${i}`, 0]
}

for (let n = 0; n < count; n++) {
  prompt.sample.inputs.seed = Math.floor(Math.random() * 2 ** 48)
  const started = Date.now()
  const res = await fetch(`${COMFY}/prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, client_id: 'claude-girl' })
  })
  const body = await res.json()
  if (!res.ok || body.error) {
    console.error(JSON.stringify(body, null, 2))
    process.exit(1)
  }
  const id = body.prompt_id
  for (;;) {
    await new Promise(r => setTimeout(r, 3000))
    const entry = (await (await fetch(`${COMFY}/history/${id}`)).json())[id]
    if (!entry) continue
    if (entry.status?.status_str === 'error') {
      const msg = entry.status.messages?.find(m => m[0] === 'execution_error')?.[1]
      console.error(`失败：${msg?.exception_message ?? JSON.stringify(entry.status)}`)
      process.exit(1)
    }
    if (entry.status?.completed) {
      const img = entry.outputs?.save?.images?.[0]
      console.log(`${name} 第 ${n + 1}/${count} 张：${img?.filename}（seed ${prompt.sample.inputs.seed}，${Math.round((Date.now() - started) / 1000)} 秒）`)
      break
    }
  }
}
