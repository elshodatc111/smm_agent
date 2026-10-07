import { lazy, Suspense, ComponentType } from 'react'
import { PageSkeleton } from '../components/ui'
import { GenericPage } from '../components/Blocks'
import { ErrorPage, NeedBusiness } from './Errors'

// Sahifalar kerak bo'lganda yuklanadi (boshlang'ich yuklash tezroq)
const L = (load: () => Promise<Record<string, any>>, name: string) => lazy<ComponentType<{ d: any }>>(() => load().then((m) => ({ default: m[name] })))
const Dashboard = L(() => import('./Dashboard'), 'Dashboard')
const DashboardAll = L(() => import('./Dashboard'), 'DashboardAll')
const Calendar = L(() => import('./Calendar'), 'Calendar')
const ContentForm = L(() => import('./ContentForm'), 'ContentForm')
const ContentDetail = L(() => import('./ContentDetail'), 'ContentDetail')
const Cloud = L(() => import('./Cloud'), 'Cloud')
const Settings = L(() => import('./Settings'), 'Settings')
const Notifications = L(() => import('./Misc'), 'Notifications')
const Audit = L(() => import('./Misc'), 'Audit')
const Activity = L(() => import('./Misc'), 'Activity')
const Guide = L(() => import('./Misc'), 'Guide')
const Health = L(() => import('./Misc'), 'Health')
const RoleMatrix = L(() => import('./Misc'), 'RoleMatrix')
const MediaDetail = L(() => import('./Misc'), 'MediaDetail')
const ContentChoose = L(() => import('./Misc'), 'ContentChoose')
const PostList = L(() => import('./Misc'), 'PostList')
const PostInsight = L(() => import('./Misc'), 'PostInsight')

export function renderPage(d: any) {
  return <Suspense fallback={<PageSkeleton />}>{pick(d)}</Suspense>
}

function pick(d: any) {
  switch (d.kind) {
    case 'page': return <GenericPage data={d} />
    case 'dashboard': return <Dashboard d={d} />
    case 'dashboard_all': return <DashboardAll d={d} />
    case 'calendar': return <Calendar d={d} />
    case 'content_form': return <ContentForm d={d} />
    case 'content_detail': return <ContentDetail d={d} />
    case 'content_choose': return <ContentChoose d={d} />
    case 'cloud': return <Cloud d={d} />
    case 'settings': return <Settings d={d} />
    case 'notifications': return <Notifications d={d} />
    case 'audit': return <Audit d={d} />
    case 'activity': return <Activity d={d} />
    case 'guide': return <Guide d={d} />
    case 'health': return <Health d={d} />
    case 'role_matrix': return <RoleMatrix d={d} />
    case 'media_detail': return <MediaDetail d={d} />
    case 'post_list': return <PostList d={d} />
    case 'post_insight': return <PostInsight d={d} />
    case 'need_business': return <NeedBusiness d={d} />
    case 'error': return <ErrorPage status={d.status} title={d.title} detail={d.detail} onHome={() => (location.href = '/app/')} />
    case 'login': return <PageSkeleton />
    default: return <ErrorPage status={0} title="Noma'lum sahifa turi" detail={String(d.kind)} onHome={() => (location.href = '/app/')} />
  }
}
