/* GoOrGrow motion layer (GSAP).
   Everything visual that moves lives here; app.js only calls Motion.* at the right moments.
   If someone prefers reduced motion, every function finishes instantly. */
(() => {
  const ok = typeof gsap !== "undefined";
  const reduce = !ok || matchMedia("(prefers-reduced-motion: reduce)").matches;
  const M = { reduce, enabled: ok && !reduce };
  window.Motion = M;
  if (!ok) { M.transition = (from, to) => { if (from) from.hidden = true; to.hidden = false; return Promise.resolve(); }; return; }

  gsap.registerPlugin(SplitText, ScrollTrigger, DrawSVGPlugin, CustomEase, MotionPathPlugin);
  CustomEase.create("swoop", "M0,0 C0.25,0.1 0.25,1 1,1");
  document.documentElement.classList.toggle("gsap-on", M.enabled);
  const done = () => Promise.resolve();

  /* ---------------- haptic clicks ----------------
     Every button squishes when pressed and springs back, with a ripple from the click point.
     On phones that support it, a tiny vibration too. */
  let pressed = null;
  document.addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".btn, .chip, .seg button, .replay, .doodle-hit, .tab");
    if (!b || b.disabled) return;
    try { navigator.vibrate && navigator.vibrate(8); } catch (_) {}
    if (reduce) return;
    pressed = b;
    gsap.to(b, { scale: 0.94, duration: 0.08, ease: "power2.out" });
    if (b.matches(".btn, .chip, .tab")) {
      const r = b.getBoundingClientRect(), dot = document.createElement("span");
      dot.className = "ripple";
      dot.style.left = e.clientX - r.left + "px"; dot.style.top = e.clientY - r.top + "px";
      b.appendChild(dot);
      gsap.fromTo(dot, { scale: 0, opacity: 0.35 }, { scale: Math.max(r.width, r.height) / 6, opacity: 0, duration: 0.6, ease: "power2.out", onComplete: () => dot.remove() });
    }
  });
  const release = () => {
    if (!pressed) return;
    gsap.to(pressed, { scale: 1, duration: 0.6, ease: "elastic.out(1.1, 0.4)" });
    pressed = null;
  };
  ["pointerup", "pointercancel", "dragend"].forEach((t) => document.addEventListener(t, release));

  /* ---------------- step progress line ---------------- */
  M.progress = (step) => {
    const line = document.querySelector(".steps-line i");
    if (line) gsap.to(line, { scaleX: Math.max(0.04, (step - 1) / 3), duration: reduce ? 0 : 0.8, ease: "power3.inOut" });
  };

  /* ---------------- page transitions ----------------
     Changing step: a pine panel sweeps up with the step name, then the next page builds in.
     Same step (e.g. upload -> profile): the old page slides away left, the new one slides in. */
  const curtain = () => document.getElementById("curtain");
  M.enter = (view) => {
    if (reduce) return done();
    const kids = [...view.children].filter((k) => !k.hidden && k.offsetParent !== null);
    return gsap.fromTo(kids, { y: 28, opacity: 0 }, { y: 0, opacity: 1, duration: 0.55, ease: "power3.out", stagger: 0.06, clearProps: "transform,opacity" }).then();
  };
  M.transition = (from, to, { label, newStep } = {}) => {
    const swap = () => { if (from) from.hidden = true; to.hidden = false; window.scrollTo(0, 0); };
    if (reduce || !from || from === to) { swap(); return done(); }
    if (newStep && label) {
      const c = curtain(), t = c.querySelector("span");
      t.textContent = label;
      const split = SplitText.create(t, { type: "words,chars", wordsClass: "word", charsClass: "char" });
      return gsap.timeline()
        .set(c, { display: "grid", yPercent: 100 })
        .to(c, { yPercent: 0, duration: 0.5, ease: "power4.inOut" })
        .from(split.chars, { yPercent: 120, opacity: 0, duration: 0.4, stagger: 0.02, ease: "back.out(2)" }, "-=0.15")
        .call(swap)
        .to(c, { yPercent: -100, duration: 0.55, ease: "power4.inOut" }, "+=0.18")
        .set(c, { display: "none" })
        .call(() => { split.revert(); M.enter(to); }, null, "-=0.3")
        .then();
    }
    return gsap.timeline()
      .to(from, { x: -40, opacity: 0, duration: 0.25, ease: "power2.in" })
      .call(swap)
      .set(from, { clearProps: "transform,opacity" })
      .call(() => M.enter(to))
      .then();
  };

  /* ---------------- first page ---------------- */
  M.heroIntro = () => {
    const hero = document.querySelector(".hero");
    if (!hero || reduce) return;
    const split = SplitText.create(hero, { type: "chars,words", charsClass: "char" });
    const tl = gsap.timeline({ delay: 0.15 });
    tl.from(split.chars, { yPercent: 115, rotate: 7, opacity: 0, duration: 0.75, ease: "back.out(1.7)", stagger: 0.022 })
      .from("#ink path", { drawSVG: 0, duration: 0.6, ease: "power2.inOut" }, "-=0.35")
      .from("#v-upload .lede", { y: 16, opacity: 0, duration: 0.5 }, "-=0.35")
      .from("#drop", { y: 30, opacity: 0, scale: 0.97, duration: 0.6, ease: "power3.out" }, "-=0.3")
      .from("#v-upload > .field, #btn-read", { y: 20, opacity: 0, duration: 0.45, stagger: 0.07 }, "-=0.35")
      .from(".doodle path", { drawSVG: 0, duration: 0.9, stagger: 0.08, ease: "power1.inOut" }, 0.7)
      .call(startDoodles);
    // Letters spring up when you hover them.
    split.chars.forEach((ch) => ch.addEventListener("mouseenter", () =>
      gsap.fromTo(ch, { y: 0 }, { y: -10, duration: 0.18, yoyo: true, repeat: 1, ease: "power2.out" })));
  };

  let doodlesStarted = false;
  function startDoodles() {
    if (doodlesStarted) return;
    doodlesStarted = true;
    // Gentle float, each at its own pace.
    gsap.utils.toArray(".doodle").forEach((d, i) => {
      gsap.to(d, { y: "+=8", rotate: i % 2 ? 4 : -4, duration: 2.4 + i * 0.3, yoyo: true, repeat: -1, ease: "sine.inOut" });
    });
    // Sparkle twinkles.
    gsap.to(".d-star", { scale: 1.25, transformOrigin: "50% 50%", duration: 0.7, yoyo: true, repeat: -1, ease: "sine.inOut" });
    // Paper plane loops along its dashed trail.
    const plane = document.querySelector("#plane");
    if (plane) {
      gsap.to(plane, { motionPath: { path: "#plane-trail", align: "#plane-trail", alignOrigin: [0.5, 0.5], autoRotate: true },
        duration: 5, repeat: -1, repeatDelay: 1.2, ease: "power1.inOut" });
    }
    // Doodles drift away from the cursor a little (each at a different depth).
    const layer = document.querySelector(".doodles");
    if (!layer) return;
    const items = gsap.utils.toArray(".doodle").map((el, i) => ({
      x: gsap.quickTo(el, "x", { duration: 0.8, ease: "power3.out" }),
      y: gsap.quickTo(el, "y", { duration: 0.8, ease: "power3.out" }),
      depth: 6 + (i % 4) * 5,
    }));
    window.addEventListener("pointermove", (e) => {
      const nx = e.clientX / innerWidth - 0.5, ny = e.clientY / innerHeight - 0.5;
      items.forEach((it) => { it.x(-nx * it.depth * 2); it.y(-ny * it.depth); });
    });
    // Click a doodle: it does a little trick.
    document.querySelectorAll(".doodle-hit").forEach((el) => el.addEventListener("click", () => {
      gsap.fromTo(el, { rotate: 0 }, { rotate: 360, scale: 1.2, duration: 0.7, ease: "back.out(1.6)", onComplete: () => gsap.to(el, { scale: 1, duration: 0.3 }) });
    }));
  }

  // Drop zone follows the cursor slightly, and celebrates when a file arrives.
  M.dropMagnet = (drop) => {
    if (reduce || !drop) return;
    const qx = gsap.quickTo(drop, "x", { duration: 0.5, ease: "power3.out" }), qy = gsap.quickTo(drop, "y", { duration: 0.5, ease: "power3.out" });
    drop.addEventListener("pointermove", (e) => {
      const r = drop.getBoundingClientRect();
      qx((e.clientX - r.left - r.width / 2) * 0.03); qy((e.clientY - r.top - r.height / 2) * 0.06);
    });
    drop.addEventListener("pointerleave", () => { qx(0); qy(0); });
  };
  M.fileAdded = (li) => {
    if (reduce || !li) return;
    gsap.from(li, { y: -20, scale: 0.8, opacity: 0, duration: 0.6, ease: "elastic.out(1, 0.5)" });
    const tick = document.querySelector("#drop-tick");
    if (tick) gsap.fromTo(tick, { drawSVG: 0, opacity: 1 }, { drawSVG: "100%", duration: 0.5, ease: "power2.out" });
    gsap.fromTo(".d-arrow", { rotate: 0 }, { rotate: -12, duration: 0.15, yoyo: true, repeat: 3, transformOrigin: "50% 0%" });
  };

  /* ---------------- lists that build in ---------------- */
  M.stagger = (els, opts = {}) => {
    if (reduce || !els || !els.length) return;
    gsap.from(els, { y: 14, opacity: 0, duration: 0.45, stagger: opts.stagger ?? 0.04, ease: opts.ease || "back.out(1.6)", clearProps: "transform,opacity" });
  };
  M.pop = (el) => {
    if (reduce || !el) return;
    gsap.fromTo(el, { scale: 0.9 }, { scale: 1, duration: 0.5, ease: "elastic.out(1.2, 0.4)" });
  };

  /* ---------------- loading scan ---------------- */
  M.scanStep = () => {
    const beam = document.querySelector(".scan-doc b");
    if (reduce || !beam) return gsap.delayedCall(0.6, () => {}).then();
    return gsap.fromTo(beam, { top: "0%" }, { top: "100%", duration: 0.6, ease: "sine.inOut" }).then();
  };

  /* ---------------- results ---------------- */
  M.results = () => {
    if (reduce) return;
    const tl = gsap.timeline({ delay: 0.25 });
    tl.from(".flag-col", { y: 30, opacity: 0, duration: 0.5, stagger: 0.12, ease: "power3.out", clearProps: "transform,opacity" })
      .from(".flag-col li", { y: -12, opacity: 0, duration: 0.3, stagger: 0.035, ease: "back.out(2)", clearProps: "transform,opacity" }, "-=0.2");
    M.scores(document.querySelectorAll("#jobs .job"));
  };
  M.scores = (rows) => {
    rows.forEach((row) => {
      const bar = row.querySelector(".bar i"), num = row.querySelector(".score-num");
      if (!bar || !num) return;
      const to = +num.dataset.to;
      if (reduce) { num.textContent = to; bar.style.width = to + "%"; return; }
      const obj = { v: 0 };
      gsap.timeline({ scrollTrigger: { trigger: row, start: "top 90%", once: true } })
        .from(row, { x: -24, opacity: 0, duration: 0.45, ease: "power2.out", clearProps: "transform,opacity" })
        .to(obj, { v: to, duration: 1, ease: "power2.out", onUpdate: () => (num.textContent = Math.round(obj.v)) }, "<")
        .fromTo(bar, { width: 0 }, { width: to + "%", duration: 1, ease: "power2.out" }, "<");
    });
    ScrollTrigger.refresh();
  };

  /* ---------------- GO / GROW ---------------- */
  let goSplit, growSplit, trackLoop, hoverBound = false;
  M.choiceIntro = () => {
    const split = document.getElementById("split");
    if (!split) return;
    goSplit && goSplit.revert(); growSplit && growSplit.revert();
    goSplit = SplitText.create("#pick-go .big", { type: "chars", charsClass: "char" });
    growSplit = SplitText.create("#pick-grow .big", { type: "chars", charsClass: "char" });
    gsap.set(split, { gridTemplateColumns: "1fr 1fr" });
    gsap.set(["#pick-go", "#pick-grow", "#pick-go .what", "#pick-grow .what", ".sprout", ".sprout .leaf", "#stem"], { clearProps: "all" });
    if (reduce) return;
    gsap.set("#track", { strokeDasharray: "10 14" });
    trackLoop && trackLoop.kill();
    trackLoop = gsap.to("#track", { strokeDashoffset: -48, duration: 1, ease: "none", repeat: -1 });
    gsap.timeline()
      .from(goSplit.chars, { yPercent: 100, opacity: 0, duration: 0.6, stagger: 0.05, ease: "back.out(2)" }, 0.2)
      .from(growSplit.chars, { yPercent: 100, opacity: 0, duration: 0.6, stagger: 0.05, ease: "back.out(2)" }, 0.3);
    if (hoverBound) return;
    hoverBound = true;
    ["go", "grow"].forEach((side) => {
      const el = document.getElementById("pick-" + side), other = document.getElementById("pick-" + (side === "go" ? "grow" : "go"));
      el.addEventListener("mouseenter", () => {
        if (split.dataset.chosen) return;
        gsap.to(split, { gridTemplateColumns: side === "go" ? "1.15fr 0.85fr" : "0.85fr 1.15fr", duration: 0.6, ease: "power3.out" });
        gsap.to((side === "go" ? goSplit : growSplit).chars, { y: -12, duration: 0.4, stagger: 0.04, ease: "back.out(3)" });
        gsap.to(other, { filter: "saturate(0.55) brightness(0.92)", duration: 0.4 });
      });
      el.addEventListener("mouseleave", () => {
        if (split.dataset.chosen) return;
        gsap.to(split, { gridTemplateColumns: "1fr 1fr", duration: 0.6, ease: "power3.out" });
        gsap.to((side === "go" ? goSplit : growSplit).chars, { y: 0, duration: 0.4, stagger: 0.03 });
        gsap.to(other, { filter: "none", duration: 0.4 });
      });
    });
  };
  M.choiceReset = () => { const s = document.getElementById("split"); if (s) delete s.dataset.chosen; };

  function sparks(from, color, count, dir) {
    const split = document.getElementById("split"), box = split.getBoundingClientRect(), r = from.getBoundingClientRect();
    for (let i = 0; i < count; i++) {
      const s = document.createElement("span");
      s.className = "spark"; s.style.background = color;
      s.style.left = r.left - box.left + r.width * Math.random() + "px";
      s.style.top = r.top - box.top + r.height * Math.random() + "px";
      split.appendChild(s);
      gsap.to(s, { x: dir === "right" ? gsap.utils.random(120, 420) : gsap.utils.random(-90, 90),
        y: dir === "right" ? gsap.utils.random(-70, 70) : gsap.utils.random(-280, -80),
        opacity: 0, scale: gsap.utils.random(0.4, 1.4), duration: gsap.utils.random(0.6, 1.1), ease: "power2.out", onComplete: () => s.remove() });
    }
  }

  M.choose = (choice) => {
    const split = document.getElementById("split");
    split.dataset.chosen = choice;
    try { navigator.vibrate && navigator.vibrate([12, 40, 18]); } catch (_) {}
    if (reduce) return done();
    if (choice === "go") {
      return gsap.timeline()
        .to(split, { gridTemplateColumns: "1fr 0fr", duration: 0.7, ease: "power4.inOut" })
        .to("#pick-grow", { opacity: 0, padding: 0, duration: 0.3 }, "<")
        .to(goSplit.chars, { x: -18, duration: 0.25, ease: "power2.in", stagger: 0.03 }, "-=0.2")
        .call(() => sparks(document.querySelector("#pick-go .big"), "#fff", 28, "right"))
        .to(goSplit.chars, { x: "120vw", skewX: -18, duration: 0.7, ease: "power4.in", stagger: 0.06 })
        .fromTo("#track", { drawSVG: "0%" }, { drawSVG: "100%", duration: 0.6, ease: "power2.out" }, "<")
        .to("#pick-go .what, #pick-go .count, #pick-go .sugg", { y: -10, opacity: 0, duration: 0.3 }, "<0.2")
        .then();
    }
    // Same as the approved preview: the sprout regrows from the ground up, then the word sprouts up.
    gsap.set(".sprout .leaf", { transformOrigin: "50% 100%", scale: 0 });
    return gsap.timeline()
      .to(split, { gridTemplateColumns: "0fr 1fr", duration: 0.7, ease: "power4.inOut" })
      .to("#pick-go", { opacity: 0, padding: 0, duration: 0.3 }, "<")
      .to("#pick-grow .sugg", { opacity: 0, duration: 0.2 }, "<")
      .fromTo("#stem", { drawSVG: "0%" }, { drawSVG: "100%", duration: 0.9, ease: "power2.out" })
      .fromTo(".sprout .leaf", { scale: 0 }, { scale: 1, duration: 0.7, ease: "elastic.out(1, 0.45)", stagger: 0.18 }, "-=0.35")
      .to(".sprout", { scale: 1.35, y: -20, duration: 0.8, ease: "power2.inOut" }, "-=0.4")
      .from(growSplit.chars, { y: 40, duration: 0.6, ease: "back.out(3)", stagger: 0.06 }, "<")
      .call(() => sparks(document.querySelector(".sprout"), "#D9F2C9", 18, "up"), null, "<0.2")
      .to({}, { duration: 0.5 })
      .then();
  };
})();
