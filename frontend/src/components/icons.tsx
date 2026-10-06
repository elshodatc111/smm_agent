import { Home, BarChart3, Activity, Users, CalendarDays, CheckSquare, Lightbulb, Sparkles, ScrollText, Send, Cloud, Film, Trash2, Briefcase, Link2, Megaphone, FileText, Tag, History, Bell, Settings, BookOpen, LayoutGrid, Plug, Palette, Image as ImageIcon } from 'lucide-react'

const MAP: Record<string, any> = {
  home: Home, chart: BarChart3, pulse: Activity, users: Users, cal: CalendarDays, check: CheckSquare, bulb: Lightbulb, spark: Sparkles, scroll: ScrollText,
  send: Send, cloud: Cloud, film: Film, trash: Trash2, brief: Briefcase, link: Link2, mega: Megaphone, file: FileText, tag: Tag, history: History, bell: Bell, gear: Settings,
  book: BookOpen, plug: Plug, palette: Palette, image: ImageIcon,
}
export function Icon({ name, className = 'w-[18px] h-[18px]' }: { name: string; className?: string }) {
  const C = MAP[name] || LayoutGrid
  return <C className={className} />
}
