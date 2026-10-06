import { useParams } from 'react-router';
import { ErrorNote, Spinner } from '@/components/ui';
import { GoalEditor } from '@/features/design/GoalEditor';
import { useProject } from '@/features/project/useProject';
import { loadGoal } from '@/lib/goalStore';

export default function Goal() {
  const { projectId = 'perov5-demo' } = useParams();
  const { data: project, error, loading, reload } = useProject(projectId);
  if (loading) return <Spinner label="Loading the project" />;
  if (error || !project) return <ErrorNote error={error} retry={reload} />;
  return (
    <>
      <div className="page-head">
        <h1>Define the design goal</h1>
        <p>{project.title}: {project.description}</p>
      </div>
      <GoalEditor project={project} initial={loadGoal(project.project_id, project.default_goal)} />
    </>
  );
}
