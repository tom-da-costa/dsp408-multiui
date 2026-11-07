/** Call `fn` at most every `interval` ms, always delivering the latest value. */
export function throttleLatest<T>(fn: (value: T) => void, interval: number) {
  let last = 0;
  let pending: { value: T } | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const fire = () => {
    timer = null;
    if (pending) {
      last = Date.now();
      const { value } = pending;
      pending = null;
      fn(value);
    }
  };

  return {
    push(value: T) {
      pending = { value };
      const wait = interval - (Date.now() - last);
      if (wait <= 0) {
        if (timer) clearTimeout(timer);
        fire();
      } else if (!timer) {
        timer = setTimeout(fire, wait);
      }
    },
    flush() {
      if (timer) clearTimeout(timer);
      fire();
    },
  };
}
