import { type HTMLAttributes, type ReactNode } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const cardVariants = cva('rounded-xl transition-all duration-300', {
  variants: {
    variant: {
      default: 'glass-card',
      panel: 'glass-panel rounded-xl',
      flat: 'bg-surface border border-border rounded-xl',
      ghost: 'bg-transparent border border-border/50 rounded-xl hover:border-border',
      accent: [
        'glass-card border-accent/20',
        'hover:border-accent/40 hover:shadow-accent-glow-sm',
      ].join(' '),
    },
    padding: {
      none: '',
      sm: 'p-4',
      md: 'p-5',
      lg: 'p-6',
      xl: 'p-8',
    },
  },
  defaultVariants: { variant: 'default', padding: 'md' },
})

export interface CardProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {}

function Card({ className, variant, padding, ...props }: CardProps) {
  return (
    <div
      className={cn(cardVariants({ variant, padding }), className)}
      {...props}
    />
  )
}

interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  title?: string
  description?: string
  action?: ReactNode
}

function CardHeader({ className, title, description, action, children, ...props }: CardHeaderProps) {
  return (
    <div className={cn('flex items-start justify-between gap-3 mb-4', className)} {...props}>
      <div className="flex-1 min-w-0">
        {title && (
          <h3 className="text-base font-semibold text-text-primary truncate">{title}</h3>
        )}
        {description && (
          <p className="text-sm text-text-secondary mt-0.5">{description}</p>
        )}
        {children}
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  )
}

function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('', className)} {...props} />
}

function CardFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('flex items-center gap-3 mt-4 pt-4 border-t border-border/50', className)}
      {...props}
    />
  )
}

export { Card, CardContent, CardFooter, CardHeader, cardVariants }
