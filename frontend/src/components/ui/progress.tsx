'use client'

import * as ProgressPrimitive from '@radix-ui/react-progress'
import { type ComponentPropsWithoutRef, type ElementRef, forwardRef } from 'react'
import { cn } from '@/lib/utils'

interface ProgressProps extends ComponentPropsWithoutRef<typeof ProgressPrimitive.Root> {
  value?: number
  variant?: 'default' | 'success' | 'warning' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  showLabel?: boolean
  label?: string
  animated?: boolean
}

const variantClasses = {
  default: 'bg-accent',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
}

const sizeClasses = {
  sm: 'h-1',
  md: 'h-2',
  lg: 'h-3',
}

const Progress = forwardRef<
  ElementRef<typeof ProgressPrimitive.Root>,
  ProgressProps
>(({ className, value = 0, variant = 'default', size = 'md', showLabel, label, animated, ...props }, ref) => (
  <div className="w-full space-y-1.5">
    {(showLabel || label) && (
      <div className="flex items-center justify-between text-xs">
        {label && <span className="text-text-secondary">{label}</span>}
        {showLabel && <span className="text-text-muted font-medium">{Math.round(value)}%</span>}
      </div>
    )}
    <ProgressPrimitive.Root
      ref={ref}
      className={cn(
        'relative overflow-hidden rounded-full bg-surface',
        sizeClasses[size],
        className
      )}
      value={value}
      {...props}
    >
      <ProgressPrimitive.Indicator
        className={cn(
          'h-full w-full flex-1 rounded-full transition-all duration-500 ease-out',
          variantClasses[variant],
          animated && 'animate-pulse'
        )}
        style={{ transform: `translateX(-${100 - (value ?? 0)}%)` }}
      />
    </ProgressPrimitive.Root>
  </div>
))

Progress.displayName = ProgressPrimitive.Root.displayName

export { Progress }
