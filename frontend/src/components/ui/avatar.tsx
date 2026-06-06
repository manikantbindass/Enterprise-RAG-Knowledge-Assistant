'use client'

import * as AvatarPrimitive from '@radix-ui/react-avatar'
import { type ComponentPropsWithoutRef, type ElementRef, forwardRef } from 'react'
import { cn, getInitials } from '@/lib/utils'

const AvatarRoot = forwardRef<
  ElementRef<typeof AvatarPrimitive.Root>,
  ComponentPropsWithoutRef<typeof AvatarPrimitive.Root>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Root
    ref={ref}
    className={cn(
      'relative flex shrink-0 overflow-hidden rounded-full',
      className
    )}
    {...props}
  />
))
AvatarRoot.displayName = AvatarPrimitive.Root.displayName

const AvatarImage = forwardRef<
  ElementRef<typeof AvatarPrimitive.Image>,
  ComponentPropsWithoutRef<typeof AvatarPrimitive.Image>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Image
    ref={ref}
    className={cn('aspect-square h-full w-full object-cover', className)}
    {...props}
  />
))
AvatarImage.displayName = AvatarPrimitive.Image.displayName

const AvatarFallback = forwardRef<
  ElementRef<typeof AvatarPrimitive.Fallback>,
  ComponentPropsWithoutRef<typeof AvatarPrimitive.Fallback>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Fallback
    ref={ref}
    className={cn(
      'flex h-full w-full items-center justify-center rounded-full',
      'bg-accent/20 text-accent-light font-semibold text-sm',
      className
    )}
    {...props}
  />
))
AvatarFallback.displayName = AvatarPrimitive.Fallback.displayName

// ─── Composed Avatar Component ────────────────────────────────
interface AvatarProps {
  src?: string
  name?: string
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  className?: string
  online?: boolean
}

const sizeClasses = {
  xs: 'h-6 w-6 text-xs',
  sm: 'h-8 w-8 text-xs',
  md: 'h-9 w-9 text-sm',
  lg: 'h-11 w-11 text-base',
  xl: 'h-14 w-14 text-lg',
}

function Avatar({ src, name, size = 'md', className, online }: AvatarProps) {
  return (
    <div className="relative inline-flex flex-shrink-0">
      <AvatarRoot className={cn(sizeClasses[size], className)}>
        {src && (
          <AvatarImage src={src} alt={name || 'User avatar'} />
        )}
        <AvatarFallback>
          {name ? getInitials(name) : '?'}
        </AvatarFallback>
      </AvatarRoot>
      {online !== undefined && (
        <span
          className={cn(
            'absolute bottom-0 right-0 block rounded-full ring-2 ring-background',
            size === 'xs' ? 'h-1.5 w-1.5' : size === 'sm' ? 'h-2 w-2' : 'h-2.5 w-2.5',
            online ? 'bg-success' : 'bg-text-muted'
          )}
        />
      )}
    </div>
  )
}

export { Avatar, AvatarFallback, AvatarImage, AvatarRoot }
