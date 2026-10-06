import { PageSkeleton } from '../components/ui'
import { GenericPage } from '../components/Blocks'
import { Dashboard, DashboardAll } from './Dashboard'
import { Activity, Audit, ContentChoose, Guide, Health, MediaDetail, NeedBusiness, Notifications, PostInsight, PostList, RoleMatrix, ErrorPage } from './Misc'
import { Calendar } from './Calendar'
import { ContentForm } from './ContentForm'
import { ContentDetail } from './ContentDetail'
import { Cloud } from './Cloud'
import { Settings } from './Settings'

export function renderPage(d: any) {
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
