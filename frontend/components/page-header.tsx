export function PageHeader({
  title,
  description,
  badge
}: {
  title: string;
  description: string;
  badge?: string;
}) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {badge ? <div className="badge">{badge}</div> : null}
    </div>
  );
}
