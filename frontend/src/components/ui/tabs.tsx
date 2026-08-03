import * as TabsPrimitive from "@radix-ui/react-tabs";
import type { ComponentPropsWithoutRef, ElementRef } from "react";
import { forwardRef } from "react";

export const Tabs = TabsPrimitive.Root;

export const TabsList = forwardRef<
  ElementRef<typeof TabsPrimitive.List>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className = "", ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={`flex w-full flex-wrap items-stretch gap-0 border-b border-border ${className}`.trim()}
    {...props}
  />
));
TabsList.displayName = TabsPrimitive.List.displayName;

export const TabsTrigger = forwardRef<
  ElementRef<typeof TabsPrimitive.Trigger>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className = "", ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={`inline-flex min-h-9 shrink-0 cursor-pointer items-center justify-center px-3 py-2 text-sm text-muted hover:text-accent data-[state=active]:border-b-2 data-[state=active]:border-accent data-[state=active]:text-accent ${className}`.trim()}
    {...props}
  />
));
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

export const TabsContent = forwardRef<
  ElementRef<typeof TabsPrimitive.Content>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className = "", ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={`mt-4 outline-none ${className}`.trim()}
    {...props}
  />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;
