'use client';

import { useParams } from 'next/navigation';
import { useEffect } from 'react';

export default function RepoRedirect() {
  const params = useParams<{ id: string }>();
  useEffect(() => {
    window.location.replace(`/plugins/${params.id}`);
  }, [params.id]);
  return null;
}
