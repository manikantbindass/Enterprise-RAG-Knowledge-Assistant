import { cva, type VariantProps } from 'class-variance-authority'
import { type HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium border transition-colors',
  {
    variants: {
      variant: {
        default: 'badge-info',
        success: 'badge-success',
        warning: 'badge-warning',
        danger: 'badge-danger',
        muted: 'badge-muted',
        // Document statuses
        pending: 'badge-muted',
        processing: 'badge-warning',
        indexed: 'badge-success',
        failed: 'badge-danger',
        // User roles
        admin: 'bg-violet-500/15 text-violet-400 border-violet-500/30',
        manager: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
        user: 'badge-muted',
        viewer: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
        // Plans
        free: 'badge-muted',
        starter: 'badge-info',
        professional: 'bg-violet-500/15 text-violet-400 border-violet-500/30',
        enterprise: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
      },
    },
    defaultVariants: { variant: 'default' },
  }
)

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  dot?: boolean
  pulse?: boolean
}

function Badge({ className, variant, dot, pulse, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props}>
      {dot && (
        <span
          className={cn(
            'inline-block h-1.5 w-1.5 rounded-full',
            pulse && 'animate-pulse',
            variant === 'success' || variant === 'indexed'
              ? 'bg-success'
              : variant === 'warning' || variant === 'processing'
              ? 'bg-warning'
              : variant === 'danger' || variant === 'failed'
              ? 'bg-danger'
              : 'bg-current'
          )}
        />
      )}
      {children}
    </span>
  )
}

export { Badge, badgeVariants }
