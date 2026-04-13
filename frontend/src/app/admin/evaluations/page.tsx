"use client";
import { useState } from "react";
import {
  useEvaluations,
  useEvaluation,
  usePrompts,
  useCreateEvaluation,
  useDeleteEvaluation,
  useAddEvaluationTestCase,
  useDeleteEvaluationTestCase,
  useRunEvaluation,
} from "@/hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Play, Plus, Trash2, CheckCircle2, XCircle, Clock, ChevronRight } from "lucide-react";

export default function EvaluationsPage() {
  const [selectedId, setSelectedId] = useState<string>("");
  const [showCreate, setShowCreate] = useState(false);

  const { data: evaluations, isLoading } = useEvaluations();
  const { data: prompts, isLoading: promptsLoading } = usePrompts();
  const { data: current, isLoading: detailLoading } = useEvaluation(selectedId);

  const createMutation = useCreateEvaluation();
  const deleteMutation = useDeleteEvaluation();
  const addTcMutation = useAddEvaluationTestCase();
  const deleteTcMutation = useDeleteEvaluationTestCase();
  const runMutation = useRunEvaluation();

  const [newName, setNewName] = useState("");
  const [newPromptName, setNewPromptName] = useState("");
  const [newQuestion, setNewQuestion] = useState("");
  const [newExpected, setNewExpected] = useState("");

  const handleCreate = async () => {
    if (!newName.trim() || !newPromptName.trim()) return;
    try {
      const result = await createMutation.mutateAsync({
        name: newName.trim(),
        prompt_name: newPromptName.trim(),
        test_cases: [],
      });
      setSelectedId(result.id);
      setShowCreate(false);
      setNewName("");
      setNewPromptName("");
      toast.success("Tạo evaluation thành công");
    } catch {
      toast.error("Tạo evaluation thất bại");
    }
  };

  const handleAddTestCase = async () => {
    if (!selectedId || !newQuestion.trim() || !newExpected.trim()) return;
    try {
      await addTcMutation.mutateAsync({
        evaluationId: selectedId,
        body: { question: newQuestion.trim(), expected_answer: newExpected.trim() },
      });
      setNewQuestion("");
      setNewExpected("");
    } catch {
      toast.error("Thêm test case thất bại");
    }
  };

  const handleRun = async () => {
    if (!selectedId) return;
    try {
      await runMutation.mutateAsync(selectedId);
      toast.success("Chạy evaluation xong");
    } catch {
      toast.error("Chạy evaluation thất bại");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Đánh giá Prompt</h1>
        <Button onClick={() => setShowCreate(true)}><Plus className="mr-2 h-4 w-4" />Tạo mới</Button>
      </div>

      {/* Create dialog */}
      {showCreate && (
        <Card>
          <CardHeader><CardTitle>Tạo Evaluation mới</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label>Tên evaluation</Label>
                <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="VD: Prompt v2 test" />
              </div>
              <div className="space-y-1">
                <Label>Prompt</Label>
                {promptsLoading ? (
                  <div className="h-9 bg-gray-100 rounded animate-pulse" />
                ) : (
                  <Select value={newPromptName} onValueChange={(v) => v && setNewPromptName(v)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Chọn prompt" />
                    </SelectTrigger>
                    <SelectContent>
                      {prompts?.map((p) => (
                        <SelectItem key={p.name} value={p.name}>
                          {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleCreate} disabled={createMutation.isPending || !newName.trim() || !newPromptName}>Tạo</Button>
              <Button variant="outline" onClick={() => setShowCreate(false)}>Hủy</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left: Evaluation list */}
        <div className="space-y-2">
          {isLoading ? (
            <div className="text-gray-400 text-sm">Đang tải...</div>
          ) : evaluations?.length === 0 ? (
            <div className="text-gray-400 text-sm">Chưa có evaluation nào</div>
          ) : (
            evaluations?.map((ev) => (
              <Card
                key={ev.id}
                className={`cursor-pointer hover:bg-gray-50 transition-colors ${selectedId === ev.id ? "ring-2 ring-primary" : ""}`}
                onClick={() => setSelectedId(ev.id)}
              >
                <CardContent className="p-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium text-sm">{ev.name}</div>
                      <div className="text-xs text-gray-400">{ev.prompt_name}</div>
                    </div>
                    <ChevronRight className="h-4 w-4 text-gray-400" />
                  </div>
                  <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                    {ev.status === "completed" && (
                      <>
                        <span className="text-green-600 font-medium">{ev.passed ?? 0} passed</span>
                        <span className="text-red-600">{ev.failed ?? 0} failed</span>
                      </>
                    )}
                    <span className="text-gray-400">{ev.test_cases?.length ?? 0} cases</span>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>

        {/* Right: Detail */}
        <div className="lg:col-span-2 space-y-4">
          {!selectedId ? (
            <div className="text-gray-400 text-sm">Chọn một evaluation để xem chi tiết</div>
          ) : detailLoading ? (
            <div className="text-gray-400 text-sm">Đang tải...</div>
          ) : current ? (
            <>
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>{current.name}</CardTitle>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        onClick={handleRun}
                        disabled={runMutation.isPending || current.test_cases.length === 0}
                      >
                        <Play className="mr-1 h-4 w-4" />
                        {runMutation.isPending ? "Đang chạy..." : "Chạy"}
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => {
                          deleteMutation.mutate(current.id);
                          setSelectedId("");
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  {current.status === "completed" && (
                    <div className="flex items-center gap-4 mt-2 text-sm">
                      <span className="text-green-600 font-medium">{current.passed ?? 0} passed</span>
                      <span className="text-red-600">{current.failed ?? 0} failed</span>
                      <span className="text-gray-400">{current.total ?? 0} total</span>
                    </div>
                  )}
                </CardHeader>
              </Card>

              {/* Add test case */}
              <Card>
                <CardHeader><CardTitle className="text-sm">Thêm Test Case</CardTitle></CardHeader>
                <CardContent className="space-y-3">
                  <div className="space-y-1">
                    <Label>Câu hỏi</Label>
                    <Textarea
                      value={newQuestion}
                      onChange={(e) => setNewQuestion(e.target.value)}
                      rows={2}
                      placeholder="Nhập câu hỏi..."
                    />
                  </div>
                  <div className="space-y-1">
                    <Label>Đáp án kỳ vọng</Label>
                    <Textarea
                      value={newExpected}
                      onChange={(e) => setNewExpected(e.target.value)}
                      rows={2}
                      placeholder="Nhập đáp án kỳ vọng..."
                    />
                  </div>
                  <Button size="sm" onClick={handleAddTestCase} disabled={addTcMutation.isPending}>
                    <Plus className="mr-1 h-4 w-4" />
                    Thêm
                  </Button>
                </CardContent>
              </Card>

              {/* Results table */}
              <Card>
                <CardHeader><CardTitle className="text-sm">Kết quả ({current.test_cases.length})</CardTitle></CardHeader>
                <CardContent>
                  {current.test_cases.length === 0 ? (
                    <div className="text-gray-400 text-sm">Chưa có test case nào</div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left">
                            <th className="pb-2 font-medium w-8">#</th>
                            <th className="pb-2 font-medium">Câu hỏi</th>
                            <th className="pb-2 font-medium">Kỳ vọng</th>
                            <th className="pb-2 font-medium">Thực tế</th>
                            <th className="pb-2 font-medium">Đánh giá</th>
                            <th className="pb-2 font-medium w-16"></th>
                          </tr>
                        </thead>
                        <tbody>
                          {current.test_cases.map((tc, i) => (
                            <tr key={tc.id} className="border-b last:border-0">
                              <td className="py-2 text-gray-400">{i + 1}</td>
                              <td className="py-2">
                                <div className="max-w-xs truncate">{tc.question}</div>
                              </td>
                              <td className="py-2">
                                <div className="max-w-xs text-green-700 bg-green-50 rounded p-2 text-xs whitespace-pre-wrap max-h-24 overflow-y-auto">
                                  {tc.expected_answer}
                                </div>
                              </td>
                              <td className="py-2">
                                {tc.actual_answer !== null ? (
                                  <div className={`max-w-xs rounded p-2 text-xs whitespace-pre-wrap max-h-24 overflow-y-auto ${tc.passed ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
                                    {tc.actual_answer}
                                  </div>
                                ) : (
                                  <div className="text-gray-400 text-xs italic">
                                    {tc.error ? `Lỗi: ${tc.error}` : "—"}
                                  </div>
                                )}
                              </td>
                              <td className="py-2">
                                {tc.judgment ? (
                                  <div className={`text-xs max-w-xs rounded p-2 ${tc.passed ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
                                    {tc.judgment}
                                  </div>
                                ) : (
                                  <div className="text-gray-400 text-xs italic">
                                    {tc.passed === null ? <Clock className="h-4 w-4" /> : "—"}
                                  </div>
                                )}
                              </td>
                              <td className="py-2">
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="text-red-500 hover:text-red-700"
                                  onClick={() => deleteTcMutation.mutate({ evaluationId: current.id, tcId: tc.id })}
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
