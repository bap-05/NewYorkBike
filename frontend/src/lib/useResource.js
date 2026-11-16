import { useEffect, useRef, useState } from "react";

export function useResource(loader, key, revision = 0) {
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const [state, setState] = useState({
    key: null,
    data: null,
    error: null,
    loading: true,
  });
  useEffect(() => {
    const controller = new AbortController();
    setState((old) => ({
      key,
      data: old.key === key ? old.data : null,
      error: null,
      loading: true,
    }));
    loaderRef
      .current(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ key, data, error: null, loading: false });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({ key, data: null, error: error.message, loading: false });
      });
    return () => controller.abort();
  }, [key, revision]);
  return state.key === key ? state : { data: null, error: null, loading: true };
}
