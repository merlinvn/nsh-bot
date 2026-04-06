import { Card, CardContent } from "@/components/ui/card";

interface Column<T> {
  header: string;
  accessor: (row: T) => React.ReactNode;
}

interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
}

export function DataTable<T>({ data, columns }: DataTableProps<T>) {
  return (
    <Card>
      <CardContent className="p-0">
        <table className="w-full">
          <thead>
            <tr className="border-b bg-gray-50 text-left">
              {columns.map((col) => (
                <th key={col.header} className="px-4 py-3 text-sm font-medium text-gray-500">
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i} className="border-b last:border-0 hover:bg-gray-50">
                {columns.map((col) => (
                  <td key={col.header} className="px-4 py-3 text-sm">
                    {col.accessor(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {data.length === 0 && <div className="p-8 text-center text-gray-400">No data</div>}
      </CardContent>
    </Card>
  );
}
