<script lang="ts">
  // English user guide, shown by Help.svelte (which holds the styles).
</script>

<section id="help-start">
  <h2>Getting started</h2>
  <p>
    This app controls one t.racks DSP (408, 206 or 204) over the network. Every phone, tablet
    or computer on the same network can open it at the same time, with the access code. All
    of them see the same settings and the live meters.
  </p>
  <ul>
    <li>
      <strong>Changes are live:</strong> moving a control changes the sound at once. Nothing
      needs to be "sent".
    </li>
    <li>
      <strong>Settings live in the DSP.</strong> To keep a setup after the DSP is switched off
      or another preset is recalled, store it in a preset (see <em>Presets</em>).
    </li>
    <li>No internet connection is needed.</li>
  </ul>
</section>

<section id="help-rail">
  <h2>The side bar</h2>
  <p>The bar on the left is the same in every view. From top to bottom:</p>
  <dl>
    <dt>»</dt>
    <dd>Unfolds the bar to show the names of the tabs; tap again to fold it.</dd>
    <dt>Status (dot and preset)</dt>
    <dd>
      The dot is green when the DSP is online, red when the DSP or the server cannot be reached: a banner at the top then says which one (<em>SERVER</em> or <em>DSP</em>). The values shown are the last known and the controls are disabled until the link comes back, by itself (<em>Retry now</em> tries at once). Below it, the preset currently in the DSP
      (U01…U20, or F00). A small orange dot means <em>unsaved changes</em>: the settings
      differ from the stored preset. <em>DEMO</em> means there is no DSP (a simulated one).
      Tap it to open <em>Presets</em>.
    </dd>
    <dt>The tabs</dt>
    <dd>One icon per view (see <em>The tabs</em>).</dd>
    <dt>👤 Your name</dt>
    <dd>The name you gave at login, as the others see it. Tap it to open <em>Settings</em>.</dd>
    <dt>✋ Take control</dt>
    <dd>Makes the other devices read-only while you work (see <em>Several people at once</em>).</dd>
    <dt>🔒 Lock screen</dt>
    <dd>Makes this device read-only until the access code is typed.</dd>
    <dt>⛶ Full screen</dt>
    <dd>Hides the browser's bars (phones and computers that allow it).</dd>
  </dl>
</section>

<section id="help-tabs">
  <h2>The tabs</h2>
  <dl>
    <dt>🎛 Live</dt>
    <dd>
      For running a show: one strip per channel with big CLIP / CMP / LIM lights, a meter
      (with markers at the compressor <em>C</em> and limiter <em>L</em> thresholds and a white
      peak line), the gain fader and MUTE. Tap a channel's name to open its page.
    </dd>
    <dt>🔗 Link</dt>
    <dd>Groups channels so that they move together, and renames them (see <em>Link</em> below).</dd>
    <dt>🔀 Matrix</dt>
    <dd>The routing grid: which inputs go to each output.</dd>
    <dt>🎚 Params</dt>
    <dd>
      One setting at a time, on all the channels you pick: Gain, Delay, EQ, Filters, Comp,
      Limit, Gate and GEQ. Most are shown as one strip per channel, side by side, to compare and
      adjust them together. EQ shows one frequency graph per channel with its band list.
    </dd>
    <dt>🔈 Channels</dt>
    <dd>
      Everything about one channel on one page: its meter with CLIP / CMP / LIM, its frequency
      response graph (with other channels' curves on top if you pick them under
      <em>Compare with</em>), and all its settings. Pick the channel in the row at the top.
    </dd>
    <dt>▥ All-in-one</dt>
    <dd>
      One column per channel with the settings you pick in the top row, in the order a system is
      set up: Name, Link, Matrix, Filters, Comp, Limit, Gain, EQ, Delay, then Gate and GEQ (inputs
      only, hidden at first). <strong>Mute</strong> sits under each meter. Handy on a computer to
      see a whole system.
    </dd>
    <dt>🚨 Too loud</dt>
    <dd>
      One big indicator for whoever sets the volume. It lights when at least one output's
      compressor or limiter is acting, and says which. Flashing now and then is fine; if it
      stays lit, turn the volume down. Its brightness is set at the bottom.
    </dd>
    <dt>🧮 Limiter calc</dt>
    <dd>
      Computes compressor and limiter thresholds that protect your speakers, from the amplifier
      gain, the speaker's power and impedance and the type of box, then applies them to the
      outputs you pick (see <em>Limiter</em> below). The threshold is rounded down to the DSP's
      0.5 dB step, or up if you choose (up to 0.5 dB above the computed value).
    </dd>
    <dt>🪄 Setup</dt>
    <dd>
      A wizard that sets up the whole DSP from your system, in four steps: the sources (stereo
      or mono); a plan where you add amplifiers and speakers (library or generic) and wire them
      to the DSP's outputs (drag from one dot to another, or tap one then the other; tap a block,
      an output or a wire to edit it); the crossovers it proposes from the speakers' ranges; then
      a summary. Each speaker has its own specs and a side (left, right or mono L+R); the outputs
      that drive sections with the same channel name form one way, their outputs linked. A
      speaker's square dot, under its input, is its link output: wire it to another speaker to bridge it (in
      parallel). It
      works out the routing, channel names, links, filters, limiters (as the limiter
      calculator) and output gains, so that every main way plays at the same level. Writing replaces every setting (delays at 0, EQ flat),
      mutes the outputs meanwhile and stores the result in the preset slot you pick.
      <strong>Every input stays muted</strong> at the end: check the system, then unmute them in
      Live, quietly first.
    </dd>
    <dt>☰ Presets</dt>
    <dd>Recall and store the DSP's presets (see <em>Presets</em>).</dd>
    <dt>⚙ Settings</dt>
    <dd>Meter refresh rate, display options, who is connected, the device (see <em>Settings</em>).</dd>
    <dt>❓ Help</dt>
    <dd>This page.</dd>
  </dl>
</section>

<section id="help-channels">
  <h2>Choosing the channels shown</h2>
  <p>
    Live, Params and All-in-one have a row of buttons above the channels: <strong>All</strong>,
    <strong>In</strong> (inputs only), <strong>Out</strong> (outputs only), then one button per
    channel (A–D for the inputs, 1–8 for the outputs, with their names). A lit button means the
    channel is shown; tap a channel to show or hide it.
  </p>
  <ul>
    <li>Each view remembers its own choice on this device (Params: one choice for all its settings).</li>
    <li>
      Each channel has its own colour, the same everywhere. Linked channels share the colour
      of their group.
    </li>
    <li>
      With <em>Merge linked channels</em> (Settings), a group of linked channels shows as one
      channel, e.g. "Out 1+5".
    </li>
    <li>The band labelled <em>IN | OUT</em> separates the inputs from the outputs.</li>
  </ul>
</section>

<section id="help-controls">
  <h2>Faders, fields and buttons</h2>
  <dl>
    <dt>Faders</dt>
    <dd>
      A fader only moves when the drag <strong>starts on its knob</strong>, so scrolling the
      page never moves one by accident. − and + move one step; hold them to repeat. Tap the
      value above a fader to type a number.
    </dd>
    <dt>Number fields</dt>
    <dd>
      − / + change the value by one step of the DSP (hold to repeat); the slider under them
      moves it quickly; tap the number to type it. Values are always rounded to what the DSP
      can store.
    </dd>
    <dt>On / Off buttons</dt>
    <dd>Lit (green) means on. MUTE and Bypass light up red when active.</dd>
    <dt>Sections</dt>
    <dd>Tap a section's title (with the › arrow) to fold or unfold it.</dd>
    <dt>EQ graph</dt>
    <dd>
      Each EQ band has a numbered dot on the frequency graph: drag it sideways for its
      frequency and up / down for its gain; with a mouse, turn the wheel over it to change its
      Q. Grey dots are bands that do nothing (off, or at 0 dB).
    </dd>
    <dt>Badges</dt>
    <dd>
      A setting marked as not verified has not been tested on a real DSP 408 yet; on a real
      DSP it can only be changed if the server was started with <code>--experimental</code>.
    </dd>
  </dl>
</section>

<section id="help-together">
  <h2>Several people at once</h2>
  <p>
    By default everyone can change everything; the last change wins, and everyone sees it at
    once.
  </p>
  <dl>
    <dt>✋ Take control</dt>
    <dd>
      While you have control, the other devices are read-only (they show who has it). Tap
      <em>Release control</em> when you are done. Control is released by itself after a while
      without any action from you (the bar shows the time left).
    </dd>
    <dt>🔒 Lock screen</dt>
    <dd>
      Makes <strong>this</strong> device read-only, for a phone or a computer left unattended:
      everything stays visible (meters included) and the view stays where it is, but nothing
      can be changed or navigated. <em>Unlock screen</em> asks for the access code. A reload
      stays locked.
    </dd>
    <dt>Master (Settings)</dt>
    <dd>
      One person can <em>Become master</em> in <em>Settings › Connected clients</em>. The master
      can <em>Disconnect</em> another client (it goes back to the login screen and must type the
      access code again) and <em>Block new connections</em>: nobody can log in any more, while
      the browsers already connected stay connected. The block ends when the master taps
      <em>Stop being master</em>, logs out, or has had the app closed for 5 minutes. To exclude
      someone: disconnect them, then block.
    </dd>
  </dl>
</section>

<section id="help-presets">
  <h2>Presets</h2>
  <p>
    A preset is a complete setup (every setting of every channel) stored in the DSP itself.
    The DSP holds 20 of them (U01–U20) plus the factory default (F00).
  </p>
  <dl>
    <dt>Recall</dt>
    <dd>
      Loads a preset: <strong>every current setting is replaced</strong>. If the current setup
      has unsaved changes, they are lost (the app asks first). It takes a few seconds.
    </dd>
    <dt>Store</dt>
    <dd>
      Saves the current setup into a preset slot, with a name (14 plain characters at most). It
      overwrites what that slot held. F00 cannot be overwritten.
    </dd>
    <dt>Unsaved changes</dt>
    <dd>
      Shown by an orange dot in the side bar and "● unsaved changes" on this page, with a
      <em>Save to Uxx</em> button to store them into the current preset.
    </dd>
    <dt>Export / Import .prs</dt>
    <dd>
      Preset files of the official t.racks editor. <em>Export live setup</em> saves the current
      setup to a file. <em>Import .prs…</em> loads a file into the DSP (<strong>every current
      setting is replaced</strong>; the outputs are muted while it loads) and can store it in a slot
      at the same time. Matrix levels and the PEQ bypass are not carried by these files.
    </dd>
  </dl>
</section>

<section id="help-settings">
  <h2>Settings</h2>
  <dl>
    <dt>Meters · Refresh rate</dt>
    <dd>How often the meters update (1–10 times a second). It applies to every connected device.</dd>
    <dt>Meters · Scale bottom / top</dt>
    <dd>
      The range every meter shows, −40 to +20 dBu by default (+20 dBu is the DSP's full scale).
      Levels, CLIP and the colours do not change. This device only.
    </dd>
    <dt>Meters · Segments</dt>
    <dd>
      Draws the meters as a continuous bar (the default) or as segments of 1, 2, 5 or 10 dB, like
      an LED meter: a segment lights when the level reaches it and takes the colour of its top.
      This device only.
    </dd>
    <dt>Display · Merge linked channels</dt>
    <dd>
      Shows each group of linked channels as one channel in every view (except Matrix
      and Link). A change applies to the whole group; names and routing stay per channel.
      This device only.
    </dd>
    <dt>Display · Signal indicator (SIG)</dt>
    <dd>
      The level above which SIG lights (−60 dBu by default). An unconnected input reads about
      −86 dBu. This device only.
    </dd>
    <dt>Connected clients</dt>
    <dd>Everyone using the app right now, and who has control.</dd>
    <dt>Device</dt>
    <dd>
      The DSP's status, model and firmware, and the app's version. <em>Refresh from device</em>
      re-reads every setting from the DSP. <em>Disconnect from DSP and shutdown</em> stops the
      server cleanly: it lets go of the DSP (which accepts one program at a time, e.g. to use
      the t.racks editor), then stops the app for everyone. The DSP keeps its settings. Not
      possible while someone else has control or is the master.
    </dd>
    <dt>This browser</dt>
    <dd><em>Log out</em> leaves the app on this device only; the server keeps running.</dd>
  </dl>
</section>

<section id="help-audio">
  <h2>Audio settings explained</h2>
  <p>
    Each <strong>input</strong> (A–D) is a signal coming in; each <strong>output</strong> (1–8)
    feeds an amplifier. The DSP processes the inputs, sends them to the outputs (routing), and
    processes each output again.
  </p>
  <dl>
    <dt>Levels and meters (dBu)</dt>
    <dd>
      Levels are in dBu. The meters go up to +20 dBu, the most the DSP can handle:
      <strong>CLIP</strong> lights when a signal reaches it and distorts. Colours: green up to
      0 dBu, yellow up to +6, orange up to +12, red above. The level turns orange when a
      compressor acts, dark orange when a limiter acts, red on clip.
      <strong>SIG</strong> lights while a channel carries signal (above −60 dBu, adjustable in
      Settings).
    </dd>
    <dt>Gain</dt>
    <dd>The channel's volume, in dB (−60 to +12). 0 dB leaves the level as it is.</dd>
    <dt>Mute</dt>
    <dd>Silences the channel (its settings are kept).</dd>
    <dt>Phase (Ø)</dt>
    <dd>
      Inverts the signal's polarity. Useful when two speakers (e.g. a sub and a top) cancel
      each other around their crossover: try it and keep whichever sounds fuller.
    </dd>
    <dt>Delay</dt>
    <dd>
      Holds the signal back, set in milliseconds or in metres (the distance sound travels in
      that time). Used to align speakers placed at different distances from the listeners, so
      that their sound arrives together.
    </dd>
    <dt>Filters (high-pass / low-pass)</dt>
    <dd>
      A <strong>high-pass</strong> filter removes what is below its frequency (e.g. lows sent
      to a small top speaker); a <strong>low-pass</strong> removes what is above it (e.g. highs
      sent to a sub). Together they split the sound between speakers (crossover). The slope
      says how steep the cut is (6 to 48 dB per octave) and its shape: BW (Butterworth), BL
      (Bessel) or LR (Linkwitz-Riley, the usual choice to join two speakers). <em>Off</em>
      disables the filter.
    </dd>
    <dt>EQ (parametric equaliser)</dt>
    <dd>
      Up to 8 bands on the inputs, 9 on the outputs, each boosting or cutting a range of
      frequencies. A band has a <strong>type</strong> (Peak: a bell around its frequency; Low /
      High Shelf: everything below / above it; LP / HP: low-pass / high-pass; Allpass: changes
      the phase only), a <strong>frequency</strong>, a <strong>gain</strong> (+ boosts,
      − cuts) and a <strong>Q</strong> (the width: a high Q is narrow, a low Q is wide). Each
      band can be switched off, and <em>Bypass</em> disables the whole EQ.
    </dd>
    <dt>GEQ (graphic equaliser)</dt>
    <dd>On the inputs: 31 fixed bands, one per third of an octave, each with its own gain.</dd>
    <dt>Compressor</dt>
    <dd>
      On the outputs. Above its <strong>threshold</strong>, it turns the level down by its
      <strong>ratio</strong> (e.g. 1:4: 4 dB more in gives 1 dB more out; <em>Limit</em> is the
      strongest). <strong>Attack</strong> is how fast it reacts, <strong>release</strong> how
      fast it lets go, <strong>knee</strong> how gently it starts. CMP lights while it acts.
    </dd>
    <dt>Limiter</dt>
    <dd>
      On the outputs: a ceiling the output level does not go above, to protect amplifiers and
      speakers. LIM lights while it acts; if it stays lit, the system is pushed too hard. The
      <em>Limiter calc</em> tab computes a safe threshold for your speakers.
    </dd>
    <dt>Noise gate</dt>
    <dd>
      On the inputs: closes (silences) the channel while its level is below the threshold,
      e.g. to cut a microphone's background noise between phrases. Attack, hold and release
      set how fast it opens, how long it stays open, and how fast it closes.
    </dd>
    <dt>Matrix (routing)</dt>
    <dd>
      Which inputs feed each output. Tap a square to connect or disconnect an input from an
      output.
    </dd>
    <dt>Link</dt>
    <dd>
      Linked channels move together: a change to one applies to all (gain, mute, EQ, filters,
      dynamics, delay…), except their names and routing. When channels are linked, the first
      one (the lowest number) is the master: its settings are copied to the others. Used for
      stereo pairs (e.g. left and right subs). Under the channels, <em>Channel names</em> lets you
      rename each one at the same time.
    </dd>
  </dl>
</section>

<section id="help-safety">
  <h2>Good habits</h2>
  <ul>
    <li>Store your setup in a preset once it sounds right; keep a spare preset to experiment on.</li>
    <li>Turn the volume down before big changes to filters, EQ or routing.</li>
    <li>Watch the Too loud tab or the LIM lights: a limiter that stays lit means turn it down.</li>
    <li>Lock the screen of a device you leave unattended, or take control while you tune.</li>
  </ul>
</section>
