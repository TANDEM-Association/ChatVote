"use client";

import { createContext, useContext, useState } from "react";

import { type Tenant } from "@lib/firebase/firebase.types";

type Props = {
  tenant?: Tenant;
  children: React.ReactNode;
};

const TenantContext = createContext<Tenant | undefined>(undefined);

const TenantProvider = ({ children, tenant: initialTenant }: Props) => {
  const [tenant, setTenant] = useState<Tenant | undefined>(initialTenant);
  const [prevInitialTenant, setPrevInitialTenant] = useState(initialTenant);

  // Adjust state during render when initialTenant prop changes
  // Only update if initialTenant is defined and has a different id (persist tenant across re-renders)
  if (prevInitialTenant !== initialTenant) {
    setPrevInitialTenant(initialTenant);
    if (initialTenant && initialTenant.id !== tenant?.id) {
      setTenant(initialTenant);
    }
  }

  return (
    <TenantContext.Provider value={tenant}>{children}</TenantContext.Provider>
  );
};

export function useTenant() {
  return useContext(TenantContext);
}

export default TenantProvider;
