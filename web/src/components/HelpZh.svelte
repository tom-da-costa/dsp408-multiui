<script lang="ts">
  // Simplified Chinese user guide, shown by Help.svelte (which holds the styles). The rest of the
  // UI is in English, so the names of buttons and tabs stay in English here, as on screen.
</script>

<section id="help-start">
  <h2>入门</h2>
  <p>
    本应用通过网络控制一台 t.racks DSP（408、206 或 204）。同一网络中的所有手机、平板和电脑都可以凭访问码同时打开它。所有人看到的是相同的设置和实时电平表。
  </p>
  <ul>
    <li><strong>修改立即生效：</strong>移动控件会立刻改变声音，无需“发送”。</li>
    <li>
      <strong>设置保存在 DSP 中。</strong>若要在 DSP 关机或调用其他预设后保留当前设置，请将其存入预设（见<em>预设</em>）。
    </li>
    <li>无需连接互联网。</li>
  </ul>
</section>

<section id="help-rail">
  <h2>侧边栏</h2>
  <p>左侧的栏在所有视图中都相同。从上到下依次为：</p>
  <dl>
    <dt>»</dt>
    <dd>展开侧边栏以显示各标签页的名称；再点一次收起。</dd>
    <dt>状态（圆点和预设）</dt>
    <dd>
      DSP 在线时圆点为绿色。下方是 DSP 当前加载的预设（U01…U20 或 F00）。小橙点表示<em>有未保存的更改</em>：当前设置与已保存的预设不同。<em>DEMO</em>
      表示没有连接 DSP（使用的是模拟设备）。点击可打开 <em>Presets</em>。
    </dd>
    <dt>标签页</dt>
    <dd>每个视图一个图标（见<em>标签页</em>）。</dd>
    <dt>👤 你的名字</dt>
    <dd>登录时填写的名字，也是其他人看到的名字。点击可打开 <em>Settings</em>。</dd>
    <dt>✋ Take control</dt>
    <dd>在你操作期间，让其他设备变为只读（见<em>多人同时使用</em>）。</dd>
    <dt>🔒 Lock screen</dt>
    <dd>让本设备变为只读，直到输入访问码。</dd>
    <dt>⛶ Full screen</dt>
    <dd>隐藏浏览器的工具栏（适用于支持此功能的手机和电脑）。</dd>
  </dl>
</section>

<section id="help-tabs">
  <h2>标签页</h2>
  <dl>
    <dt>🎛 Live</dt>
    <dd>
      用于演出现场：每个通道一条推子条，带有大号 CLIP / CMP / LIM 指示灯、电平表（标有压缩器 <em>C</em> 和限幅器 <em>L</em>
      的阈值，以及白色峰值线）、增益推子和 MUTE。点击通道名称可打开该通道的页面。
    </dd>
    <dt>🎚 Params</dt>
    <dd>
      一次显示一项设置，作用于所有选中的通道：Gain、Delay、EQ、Filters、Comp、Limit、Gate、GEQ、Matrix 和 Link。大多数设置以每通道一条并排显示，便于比较和统一调整。EQ
      为每个通道显示一张频率响应图及其频段列表；Matrix 是路由矩阵；Link 用于将通道编组联动。
    </dd>
    <dt>🔈 Channels</dt>
    <dd>
      单个通道的全部内容集中在一页：带 CLIP / CMP / LIM 的电平表、频率响应曲线（若在 <em>Compare with</em>
      中选择其他通道，会叠加显示它们的曲线）以及所有设置。在顶部一行中选择通道。
    </dd>
    <dt>▥ All-in-one</dt>
    <dd>
      每个通道一列，显示顶部一行中选中的设置（Name、Gain、Delay、EQ、Filters、Comp、Limit、Gate、GEQ、Matrix）。适合在电脑上纵览整个系统。
    </dd>
    <dt>🚨 Too loud</dt>
    <dd>
      给调音量的人看的一个大指示灯。只要至少一个输出的压缩器或限幅器在工作，它就会亮起，并显示是哪些。偶尔闪一下没关系；如果一直亮着，就把音量调小。亮度可在下方调节。
    </dd>
    <dt>🧮 Limiter calc</dt>
    <dd>
      根据功放增益、音箱功率和阻抗以及箱体类型，计算能保护音箱的压缩器和限幅器阈值，并应用到所选输出（见下文<em>限幅器</em>）。
    </dd>
    <dt>☰ Presets</dt>
    <dd>调用和存储 DSP 的预设（见<em>预设</em>）。</dd>
    <dt>⚙ Settings</dt>
    <dd>电平表刷新率、显示选项、当前连接的用户、设备信息（见<em>设置</em>）。</dd>
    <dt>❓ Help</dt>
    <dd>本页。</dd>
  </dl>
</section>

<section id="help-channels">
  <h2>选择显示的通道</h2>
  <p>
    Live、Params 和 All-in-one 在通道上方有一排按钮：<strong>All</strong>（全部）、<strong>In</strong>（仅输入）、<strong>Out</strong>（仅输出），然后是每个通道一个按钮（输入为
    A–D，输出为 1–8，并显示其名称）。按钮亮起表示该通道正在显示；点击通道可显示或隐藏它。
  </p>
  <ul>
    <li>每个视图在本设备上记住各自的选择（Params 的所有设置共用一个选择）。</li>
    <li>每个通道有自己的颜色，在各处都相同。联动的通道共用其编组的颜色。</li>
    <li>开启 <em>Merge linked channels</em>（Settings）后，一组联动通道显示为一个通道，例如“Out 1+5”。</li>
    <li>标有 <em>IN | OUT</em> 的竖条将输入与输出分开。</li>
  </ul>
</section>

<section id="help-controls">
  <h2>推子、数值框和按钮</h2>
  <dl>
    <dt>推子</dt>
    <dd>
      只有<strong>从推子钮上开始拖动</strong>时推子才会移动，因此滚动页面不会误碰推子。− 和 + 每次调整一步；按住可连续调整。点击推子上方的数值可直接输入数字。
    </dd>
    <dt>数值框</dt>
    <dd>
      − / + 按 DSP 的一步改变数值（按住可连续调整）；下方的滑块可快速调整；点击数字可直接输入。数值总会被取整为 DSP 能保存的值。
    </dd>
    <dt>On / Off 按钮</dt>
    <dd>亮起（绿色）表示开启。MUTE 和 Bypass 生效时亮红色。</dd>
    <dt>分区</dt>
    <dd>点击分区标题（带 › 箭头）可折叠或展开该分区。</dd>
    <dt>EQ 曲线图</dt>
    <dd>
      每个 EQ 频段在频率响应图上都有一个带编号的圆点：左右拖动调整其频率，上下拖动调整其增益；使用鼠标时，在圆点上滚动滚轮可调整其 Q 值。灰色圆点表示不起作用的频段（已关闭或增益为 0 dB）。
    </dd>
    <dt>标记</dt>
    <dd>
      标有“unverified”的设置尚未在真实的 DSP 408 上测试过；在真实 DSP 上，只有服务器以 <code>--experimental</code> 启动时才能修改。
    </dd>
  </dl>
</section>

<section id="help-together">
  <h2>多人同时使用</h2>
  <p>默认情况下，所有人都可以修改所有设置；以最后一次修改为准，所有人会立刻看到。</p>
  <dl>
    <dt>✋ Take control</dt>
    <dd>
      在你掌握控制权期间，其他设备为只读（会显示是谁在控制）。完成后点击 <em>Release control</em>。如果你一段时间没有任何操作，控制权会自动释放（侧边栏会显示剩余时间）。
    </dd>
    <dt>🔒 Lock screen</dt>
    <dd>
      让<strong>本</strong>设备变为只读，适用于无人看管的手机或电脑：所有内容保持可见（包括电平表），视图保持不变，但无法修改或切换。<em>Unlock screen</em>
      需要输入访问码。刷新页面后仍保持锁定。
    </dd>
  </dl>
</section>

<section id="help-presets">
  <h2>预设</h2>
  <p>
    预设是一套完整的设置（所有通道的所有设置），保存在 DSP 本身中。DSP 可保存 20 个预设（U01–U20），另有出厂设置（F00）。
  </p>
  <dl>
    <dt>Recall</dt>
    <dd>
      加载一个预设：<strong>当前所有设置都会被替换</strong>。若当前设置有未保存的更改，这些更改将会丢失（应用会先询问）。需要几秒钟。
    </dd>
    <dt>Store</dt>
    <dd>将当前设置连同名称（最多 14 个普通字符）存入一个预设位置，会覆盖该位置原有的内容。F00 不能被覆盖。</dd>
    <dt>未保存的更改</dt>
    <dd>
      侧边栏中的橙色小点以及本页上的“● unsaved changes”表示有未保存的更改，并提供 <em>Save to Uxx</em> 按钮，可将其存入当前预设。
    </dd>
  </dl>
</section>

<section id="help-settings">
  <h2>设置</h2>
  <dl>
    <dt>Meters · Refresh rate</dt>
    <dd>电平表的刷新频率（每秒 1 到 10 次）。对所有已连接的设备生效。</dd>
    <dt>Display · Merge linked channels</dt>
    <dd>
      在所有视图中（Params › Matrix 和 Link 除外）将每组联动通道显示为一个通道。修改会作用于整个编组；名称和路由仍按通道分别设置。仅对本设备有效。
    </dd>
    <dt>Connected clients</dt>
    <dd>当前正在使用本应用的所有人，以及谁持有控制权。</dd>
    <dt>Device</dt>
    <dd>
      DSP 的状态、型号和固件，以及本应用的版本。<em>Refresh from device</em> 会从 DSP 重新读取所有设置。<em>Log out</em> 在本设备上退出应用。
    </dd>
  </dl>
</section>

<section id="help-audio">
  <h2>音频设置说明</h2>
  <p>
    每个<strong>输入</strong>（A–D）是一路进入的信号；每个<strong>输出</strong>（1–8）接一台功放。DSP 先处理各输入，再把它们分配到各输出（路由），然后再分别处理每个输出。
  </p>
  <dl>
    <dt>电平与电平表（dBu）</dt>
    <dd>
      电平以 dBu 为单位。电平表最高到 +20 dBu，即 DSP 能承受的最大值：信号达到该值并失真时 <strong>CLIP</strong>
      亮起。颜色：0 dBu 以下为绿色，+6 以下为黄色，+12 以下为橙色，更高为红色。压缩器工作时电平变为橙色，限幅器工作时变为深橙色，削波时变为红色。
    </dd>
    <dt>Gain（增益）</dt>
    <dd>通道的音量，单位 dB（−60 到 +12）。0 dB 表示电平不变。</dd>
    <dt>Mute（静音）</dt>
    <dd>关闭该通道的声音（其设置会保留）。</dd>
    <dt>Phase（Ø，相位）</dt>
    <dd>反转信号极性。当两只音箱（例如超低音和主音箱）在分频点附近互相抵消时很有用：试一试，保留听起来更饱满的那一种。</dd>
    <dt>Delay（延时）</dt>
    <dd>
      延迟信号，可用毫秒或米设置（米表示声音在这段时间内传播的距离）。用于对齐与听众距离不同的音箱，使它们的声音同时到达。
    </dd>
    <dt>滤波器（高通 / 低通）</dt>
    <dd>
      <strong>高通</strong>（high-pass）滤波器去除其频率以下的部分（例如送往小型主音箱的低频）；<strong>低通</strong>（low-pass）滤波器去除其频率以上的部分（例如送往超低音的高频）。两者配合可在音箱之间分配声音（分频）。斜率（slope）表示衰减的陡峭程度（每倍频程
      6 到 48 dB）及其类型：BW（巴特沃斯）、BL（贝塞尔）或 LR（林克维茨-瑞利，衔接两只音箱时的常用选择）。<em>Off</em> 关闭该滤波器。
    </dd>
    <dt>EQ（参量均衡器）</dt>
    <dd>
      输入最多 8 段，输出最多 9 段，每段提升或衰减一段频率范围。每段有<strong>类型</strong>（Peak：以其频率为中心的钟形；Low / High
      Shelf：其频率以下 / 以上的全部；LP / HP：低通 / 高通；Allpass：只改变相位）、<strong>频率</strong>、<strong>增益</strong>（+ 提升，− 衰减）和
      <strong>Q 值</strong>（宽度：Q 值高则窄，Q 值低则宽）。每段都可以单独关闭，<em>Bypass</em> 则关闭整个均衡器。
    </dd>
    <dt>GEQ（图示均衡器）</dt>
    <dd>用于输入：31 个固定频段，每 1/3 倍频程一段，各有独立增益。</dd>
    <dt>压缩器</dt>
    <dd>
      用于输出。电平超过<strong>阈值</strong>（threshold）后，按其<strong>压缩比</strong>（ratio）降低电平（例如 1:4：输入每多 4 dB，输出只多 1 dB；<em>Limit</em>
      为最强）。<strong>Attack</strong> 是它的反应速度，<strong>release</strong> 是它恢复的速度，<strong>knee</strong>
      是它开始压缩时的柔和程度。工作时 CMP 亮起。
    </dd>
    <dt>限幅器</dt>
    <dd>
      用于输出：输出电平不会超过的上限，用于保护功放和音箱。工作时 LIM 亮起；如果一直亮着，说明系统被推得太狠。<em>Limiter calc</em> 标签页可为你的音箱计算安全的阈值。
    </dd>
    <dt>Noise gate（噪声门）</dt>
    <dd>
      用于输入：当电平低于阈值时关闭（静音）该通道，例如在两句话之间去除话筒的底噪。Attack、hold 和 release 分别决定它打开的速度、保持打开的时间和关闭的速度。
    </dd>
    <dt>Matrix（路由）</dt>
    <dd>决定哪些输入送往各个输出。点击方格可连接或断开某个输入与某个输出。</dd>
    <dt>Link（联动）</dt>
    <dd>
      联动的通道一起变化：对其中一个的修改会作用于全部（增益、静音、均衡、滤波、动态、延时……），名称和路由除外。建立联动时，第一个通道（编号最小的）为主通道：其设置会复制到其他通道。常用于立体声对（例如左右超低音）。
    </dd>
  </dl>
</section>

<section id="help-safety">
  <h2>良好习惯</h2>
  <ul>
    <li>声音调好后立即存入预设；留一个空闲预设用于试验。</li>
    <li>在大幅修改滤波器、均衡或路由之前先调低音量。</li>
    <li>留意 Too loud 标签页或 LIM 指示灯：限幅器一直亮着就意味着要调小音量。</li>
    <li>无人看管的设备请锁屏；调音时可以先取得控制权。</li>
  </ul>
</section>
