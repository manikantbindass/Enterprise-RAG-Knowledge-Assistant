import { cva, type VariantProps } from 'class-variance-authority'
import { Loader2 } from 'lucide-react'
import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-2 rounded-lg font-medium',
    'transition-all duration-200 focus-visible:outline-none focus-visible:ring-2',
    'focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background',
    'disabled:pointer-events-none disabled:opacity-50 select-none whitespace-nowrap',
  ].join(' '),
  {
    variants: {
      variant: {
        default: [
          'bg-accent text-white hover:bg-accent-hover active:scale-[0.98]',
          'shadow-accent-glow-sm hover:shadow-accent-glow',
        ].join(' '),
        outline: [
          'border border-border bg-transparent text-text-primary',
          'hover:bg-surface hover:border-accent-light/50',
        ].join(' '),
        ghost: [
          'bg-transparent text-text-secondary hover:bg-surface hover:text-text-primary',
        ].join(' '),
        danger: [
          'bg-danger/10 text-danger border border-danger/30',
          'hover:bg-danger hover:text-white hover:border-danger',
        ].join(' '),
        success: [
          'bg-success/10 text-success border border-success/30',
          'hover:bg-success hover:text-white',
        ].join(' '),
        secondary: [
          'bg-surface text-text-primary border border-border',
          'hover:bg-surface-2 hover:border-accent/30',
        ].join(' '),
        link: 'text-accent-light underline-offset-4 hover:underline h-auto p-0',
      },
      size: {
        xs: 'h-7 px-2.5 text-xs rounded-md',
        sm: 'h-8 px-3 text-sm',
        md: 'h-9 px-4 text-sm',
        lg: 'h-10 px-6 text-base',
        xl: 'h-12 px-8 text-base',
        icon: 'h-9 w-9',
        'icon-sm': 'h-7 w-7',
        'icon-lg': 'h-11 w-11',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'md',
    },
  }
)

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, leftIcon, rightIcon, children, disabled, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          leftIcon
        )}
        {children}
        {!loading && rightIcon}
      </button>
    )
  }
)

Button.displayName = 'Button'

export { Button, buttonVariants }
