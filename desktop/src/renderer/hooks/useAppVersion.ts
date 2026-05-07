import { useEffect, useState } from 'react';
import packageInfo from '../../../package.json';
import { getAppVersion, isDesktop } from '../lib/desktop';

export function useAppVersion() {
  const [version, setVersion] = useState(packageInfo.version);

  useEffect(() => {
    if (!isDesktop) return;
    let active = true;
    getAppVersion().then((value) => {
      if (active) setVersion(value);
    }).catch(() => {
      // The package version is also available when the native bridge is unavailable.
    });
    return () => { active = false; };
  }, []);

  return version;
}
